
# Row-Level Authorization

With ERMrest, all web requests execute under daemon accounts with
eponymous PostgresQL roles:

  - All service logic as `ermrest` daemon.
  - The `ermrest` role owns all catalogs, schemas, tables,
    sequences, etc.
  - The `FORCE ROW LEVEL SECURITY` flag is set on every table.
  - The ERMrest service code tests web client context against stored
    ACLs to enforce coarse-grained access rights on catalogs.

Therefore, policy features using PostgreSQL roles are insufficient to
provide differentiated privileges to data within one catalog for
different web clients.

Row-level security is useful because it allows arbitrary boolean
expressions in the policy statements and rewrites these into all
queries executed against the database. The policies are *mixed into*
all the data access SQL generated by the ERMrest service, enforcing
row-level constraints regardless of how complex the data access
queries become.

Thus, we can effectively grant data access to the `ermrest` user only
when additional data constraints are met, considering:

  - The content of existing rows for SELECT, UPDATE, and DELETE.
  - The new or replacement row content for INSERT and UPDATE.
  - The value of `_ermrest.current_client()` scalar subquery of type `text`.
  - The value of `_ermrest.current_attributes()` scalar subquery of type `text[]`.
  - Other scalar subqueries which MAY lookup indirect values from other tables to find links between the affected row content and the current ermrest client or attributes context.

Note: row-level security policies can compute arbitrary boolean
results based on these input values. There are no built-in concepts of
ownership, access control lists, or any other privilege
model. Operations are simply allowed or denied if the boolean
expression returns a true value or not. It is up to the data modeler
in each table to decide if or how to interpret or restrict the content
of row data to make access control decisions. There is no distinction
between access control or non-access control data at the SQL nor
ERMrest protocol level.


## Performance Considerations

Because row-level security policies are effectively injecting SQL
expressions into the WHERE clauses of the other service-generated SQL
queries, they can dramatically change service performance if used
indiscriminately.

1. Avoid using scalar subqueries which access other tables on a
   row-by-row basis.
2. When calling procedures, the effective performance after query
   planning and optimization depends on the volatility class of the
   procedure, with performance descending in order: IMMUTABLE, STABLE,
   VOLATILE.
3. When calling procedures defined in pure SQL, they may be better
   optimized in recent PostgreSQL versions than procedures defined in
   PL/pgsql.
4. When calling procedures in PostgreSQL 9.6, the declaration of
   PARALLEL SAFE is required to allow parallel query plans. Other
   factors may still suppress parallelism.
5. For web applications which run many AJAX calls concurrently, there
   may be enough parallelism such that parallel plans are not
   beneficial. They help most for running a single, long-running
   query.
6. Recent versions of ERMrest define a session parameter
   `webauthn2.attributes_array` as a native text representation of a
   PostgreSQL `text[]` value. This supports faster authorization
   checks than the legacy `webauthn2.attributes` parameter which is a
   JSON serialization. It requires an updated
   `_ermrest.current_attributes()` stored procedure to have any
   benefit.
7. PostgreSQL 9.6 introduces a new function `current_setting(text,
   bool)` which can check a session parameter without throwing
   exceptions when the parameter is absent. A faster, pure SQL
   implementation of `_ermrest.current_attributes()` can exploit this.
   
A good practice to evaluate impact of row-level policies is to perform
equivalent queries through the `psql` command-line interface using
the daemon account and the `EXPLAIN ANALYZE ...` command:

- By default, `ermrest` is subject to row-level security and shows you
  how much slower it will be when queried by web clients. To emulate a
  particular web client privilege level, manually set the session
  parameters in your connection as described below.
- You can use a postgres "super-user" role to bypass row-level
  security on tables. *Caveat*: note that SQL views are executed with
  the privileges of the role owning the view, and not the role of the
  querying user. So, these views when properly owned by `ermrest` will
  not bypass row-level security on any tables they consume, even when
  queried by the super-user.
  
For this comparison to be valid, you may need to set session
parameters to a valid client context. Otherwise the SQL plan may be
significantly different due to the NULL client attributes.

Here is a more optimal stored procedure only usable with recent
ERMrest on PostgreSQL 9.6:

    CREATE OR REPLACE FUNCTION _ermrest.current_attributes() 
	RETURNS text[] STABLE PARALLEL SAFE	AS $$
	  SELECT current_setting(
	    'webauthn2.attributes_array',
	    True
	  )::text[];
	$$ LANGUAGE SQL;

This can be applied manually to an existing catalog to upgrade its
performance if you are using PostgreSQL 9.6 already. The ERMrest
code-base does not yet include such a definition as we have not yet
made a hard requirement on 9.6 features.

This variant can achieve similar performance on 9.5:

    CREATE OR REPLACE FUNCTION _ermrest.current_attributes() 
	RETURNS text[] STABLE AS $$
	  SELECT current_setting(
	    'webauthn2.attributes_array'
	  )::text[];
	$$ LANGUAGE SQL;

this procedure will raise exceptions if used in SQL session that is
not managed by ERMrest, unlike the ERMrest-supplied implementation
that uses PL/pgsql and exception handlers to catch that condition and
map it to a NULL result.

To manually simulate an ERMrest-managed client session for testing,
you can connect using the `ermrest` daemon role and manually set the
attributes. Assuming the above implementations are in place, you
would do:

    SELECT set_config(
	  'webauthn2.attributes_array',
	  (ARRAY['attr1', 'attr2']::text[])::text,
	  False
	);

or with the legacy implementation you would instead do:

    SELECT set_config(
	  'webauthn2.attributes',
	  '["attr1", "attr2"]',
	  False
	);

Where `attr1` and `attr2` are actually attribute URIs obtained from a
valid webauthn session.  If you retrieve a session object manually and
store it to `session.json`, you might obtain the list of attribute
URIs with the following Python snippet:

    import json
	
	f = open('session.json')
	s = json.load(f)
	[ a['id'] for a in s['attributes'] ]
	

## Other Considerations

Row-level security affects all access to tables for which it is
enabled. Backup database dumps could be incomplete unless taken by a
PostgreSQL superuser and/or with row level security temporarily
disabled.

We have observed problems with round-tripping of row-level security
policies from functioning databases, to dumps created by `pg_dump`,
and back to restored databases. Some important type casts and similar
may be lost in the policy that is dumped, such that PostgreSQL refuses
to load the policies again.  Thus, anyone experimenting with row-level
security SHOULD maintain an authoritative policy SQL file and be
prepared to eliminate policies from a dump, restore the modified dump,
then reapply the authoritative policies.

Other detailed issues:

1. The owner of a table bypasses row-level security unless `FORCE ROW LEVEL SECURITY` is kept on for the table.
2. DBAs SHOULD NOT attempt to introduce tables in ermrest backing databases which are not owned by the `ermrest` role.
3. DBAs SHOULD NOT attempt to introduce SQL views which are not owned by the `ermrest` role.

## Instructions and Examples

1. Upgrade your postgres to 9.5 or later
2. Have latest ERMrest master code deployed with `FORCE ROW LEVEL SECURITY` on all tables.
3. Enable row-level security on specific table
4. Create row-level policies to access table data
5. Drop or alter row-level policies by name

NOTE: the following examples use old-style group IDs as with the `goauth` webauthn provider. In the future, such group IDs will replace the `g:` prefix with a URL designating the group membership provider who asserted the group membership attribute.

### Example 1: Enable row-level security

    ALTER TABLE my_example ENABLE ROW LEVEL SECURITY;

At this point, ERMrest should still work (a smart thing to test) but data operations on this table will fail as the default policies do not allow any operations on any row data!  Go back to normal with:

    ALTER TABLE my_example DISABLE ROW LEVEL SECURITY;

### Example 2: Create row-level policies to restore all access

    CREATE POLICY select_all ON my_example FOR SELECT USING (True);
    CREATE POLICY delete_all ON my_example FOR DELETE USING (True);
    CREATE POLICY insert_all ON my_example FOR INSERT WITH CHECK (True);
    CREATE POLICY update_all ON my_example FOR UPDATE USING (True) WITH CHECK (True);

At this point, all data access is possible again.  In general, the `USING (expr)` part must evaluate to true for existing rows to be accessed while `WITH CHECK (expr)` part must evaluate true for new row content to be applied. The `USING` and `WITH CHECK` policies MAY reference column data from the existing or new row data, respectively; it is not possible to consider both existing and replacement row content in a single policy expression.

### Example 3: Drop policies to limit it again

    DROP POLICY update_all ON my_example;
    DROP POLICY insert_all ON my_example;
    DROP POLICY delete_all ON my_example;
    DROP POLICY select_all ON my_example;

### Example 4: Check against webauthn context but not row data, e.g. to emulate a table-level privilege using webauthn roles instead of PostgreSQL roles

    CREATE POLICY select_group
    ON my_example
        FOR SELECT
        USING ( 'g:f69e0a7a-99c6-11e3-95f6-12313809f035' = ANY (_ermrest.current_attributes()) );

    CREATE POLICY select_user
    ON my_example
      FOR SELECT
      USING ( 'devuser' = _ermrest.current_client() );

### Example 5: Consider row-data in more complete example, assuming the table includes `owner` and `acl` columns of type `text` and `text[]`, respectively

    -- allow members of group to insert but enforce provenance of owner column
    CREATE POLICY insert_group
    ON my_example
      FOR INSERT
      WITH CHECK (
        'g:f69e0a7a-99c6-11e3-95f6-12313809f035' = ANY (_ermrest.current_attributes())
      AND owner = _ermrest.current_client()
    );

    -- owner can update his own rows
    -- but continue to enforce provenance of owner column too
    CREATE POLICY update_owner
    ON my_example
      FOR UPDATE
      USING ( owner = _ermrest.current_client() )
      WITH CHECK ( owner = _ermrest.current_client() ) ;

    -- owner can delete his own rows
    CREATE POLICY delete_owner
      ON my_example
      FOR DELETE
      USING ( owner = _ermrest.current_client() );

    -- owner can read
    -- as can members of groups in ACL
    CREATE POLICY select_owner_acl
      ON my_example
      FOR SELECT
      USING (
        owner = _ermrest.current_client()
      OR acl && _ermrest.current_attributes()
    );