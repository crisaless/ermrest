
# ERMrest History Tracking

There is experimental support for history-tracking in ERMrest. This
feature is a work in progress and requires REST API extensions before
it is fully realized.

This document summarizes the architectural concepts and implications
that might impact a DBA or developer looking at the backend
functionality or interacting with the catalog DB.

Implementation Status:

- [x] System columns support
- [x] Stateful model with `RID` for each element
- [x] Historical tuple storage for stateful model tables
- [x] Historical tuple storage for user-defined tables
- [x] Introspection mechanism for model at revision instead of latest model
- [x] REST URL structure for access at revision
- [x] Revision timestamp normalization (fit URL param to discrete events in history)
- [x] Read-only model introspection at revision
- [x] Read-only data query at revision
- [x] Appropriate errors reject write access at revision
- [x] Appropriate errors to reject historical access to non-tracked tables or views
- [ ] Register table functions to replace view at revision?
- [x] Caching of historical models in Python
- [ ] Index acceleration of historical tuple queries?

## Overview of Design

1. The design depends heavily on new _system columns_ used throughout:
   - `RID` a numeric resource or row ID as primary key
   - `RMT` row modification timestamp
   - `RMB` row modified by client ID
   - `RCT` row creation timestamp
   - `RCB` row created by client ID
2. We now use timestamps as catalog version IDs instead of PostgreSQL transaction IDs
   - All writes by ERMrest use a serializable isolation level
   - The system clock must be monotonically increasing
   - Timestamps are stable across dump/restore events
3. The introspected catalog model is reified in tables managed by ERMrest
   - These tables assign persistent `RID` and other system columns to PostgreSQL model elements
   - `RID` assignments are stable across dump/restore events
   - Runtime introspection can dump the state of these tables quickly
   - Runtime model changes incrementally adjust these tables
   - Stored procedures can update these tables for en masse model changes by a local DBA
      - One procedure syncs by OID for incremental changes including model element renaming
	  - One procedure syncs by name for OID instability including dump/restore or DBA-driven replacement of model elements
   - All model-augmenting tables are refactored in terms of `RID` subjects
      - Annotations
	  - ACLs
	  - ACL bindings
4. We add an internal `_ermrest_history` schema to each catalog
5. We add internal tables to `_ermrest_history` corresponding to other tables in catalog
   - History tables track tuple content generically
      - `RID` corresponds to the same `RID` from the tracked table
	  - `during` is an interval `[RMT1,NULL)` when tuples are born or `[RMT1,RMT2)` when tuples have already died
	  - `RMB` corresponds to the same `RMB` from the tracked table (in case we want to show changes by client later...)
   - System tables from `_ermrest` are mapped in a simplified fashion by name
      - Table `_ermrest_history.foo` tracks table `_ermrest.foo`
	  - Tuple data is stored in a JSON blob with field `X` tracking column with name `X`
   - User tables from other schemas are mapped in a generic fashion by `RID`
      - Table `_ermrest_history.tXYZ` tracks table with `RID` `XYZ`
	  - Tuple data is stored in a JSON blob with field `ABC` tracking a column with `RID` `ABC`
	  - System columns `RID`, `RMT`, and `RMB` are lifted out of the JSON blob
6. We add triggers to automate data management
   - One trigger *before* insert or update manages system column values
   - One trigger *after* insert or update tracks tuples aka versions of rows
7. The service can query historical content at a given time or live content
   
## Historical Catalog Access via REST API

Historical access is defined in terms of a timestamp _revision_ which
SHOULD be a time in the past. Requests for a future _revision_
timestamp MAY be interpreted as *most recent known revision* which
might be non-reproducible if the same _revision_ is requested multiple
times with intervening writes to the live catalog.

### Model at Revision

Latest version of schema:

    GET /ermrest/catalog/N/schema
	
Historical version of schema:

	GET /ermrest/catalog/N@revision/schema
	
where _revision_ is a URL-encoded timestamp. Each whole schema
document will also gain a new `version` attribute at the top level to
specify the effective revision timestamp for the model it describes.

All sub-resources on the versioned catalog resource should also work
for read-only access, e.g.

	GET /ermrest/catalog/N@revision/schema/S1/table/T1/column/C1

would address a specific column `C1` in table `T1` in schema `S1`
according to the model definitions in effect at _revision_.

### Data at Revision

Queries on latest live data:

    GET /ermrest/catalog/N/entity/...
    GET /ermrest/catalog/N/attribute/...
    GET /ermrest/catalog/N/attributegroup/...
    GET /ermrest/catalog/N/aggregate/...

Queries on historical data:

    GET /ermrest/catalog/N@revision/entity/...
    GET /ermrest/catalog/N@revision/attribute/...
    GET /ermrest/catalog/N@revision/attributegroup/...
    GET /ermrest/catalog/N@revision/aggregate/...

Aside from the new `@revision` syntax in the URL, the entire read-only
catalog data API should work.

Limitation: if the query involves a table for which history collection
is not enabled, the entire request will fail. This includes explicit
joins in the entity path as well as implicit joins needed to handle
dynamic ACL bindings.

All SQL views exposed as tables will lack history collection. Any
table lacking the core system columns `RID`, `RMB`, and `RMT` will
lack history collection.  In future implementations, history
collection MAY be disabled on individual tables as a local policy
decision, even if they would otherwise support history collection.

## Accessing History within SQL

To access historical data for a history-tracked table with table
`RID`=`T1` and column `RID`=(`C1`, `C2`, ... `Ck`) at timestamp `V1`,
we can use a query similar to this:

    SELECT
	  t."RID" AS "RID",
	  d."Cx" AS "RCT",
	  lower(t.during) AS "RMT",
	  d."Cy" AS "RMT",
	  t."RMB",
	  d."C1" AS "Column name 1",
	  d."C2" AS "Column name 2",
	  ...
	  d."Ck" AS "Column name k"
	FROM _ermrest_history.tT1 t,
	LATERAL jsonb_to_record(t.rowdata) d("C1" type1, "C2" type2, ... "Ck" typek)
	WHERE t.during @> V1::timestamptz;

This approach allows us to handle three difference scenarios that can
occur during the history of the user data table:

1. A new column added after the table acquires data can implicitly add
   columns with `NULL` value without generating new storage
   tuples. The expansion of the JSON `rowdata` blob will fill in the
   missing NULL values.
2. An existing column deleted after the table acquires data can
   implicitly drop columns without generating new storage tuples. The
   expansion of the JSON `rowdata` blob will ignore extra values.
3. Renaming an existing column after the table acquires data can
   implicitly rename fields without generating new storage tuples. The
   expansion of the JSON `rowdata` blob will map the persistent
   column-level `RID` to the currently active column name.
   
As implied by the preceding, we need to be able to reconstruct the
table definition which was in effect at the time of the data revision
we wish to query. We do this by making the same sort of query to
history-tracking tables for the reified model storage. In this case,
we use a simplified history storage model where we do not use `RID`
indirection and we assume a fixed model storage table structure. Thus,
we can bootstrap the model without recursively having to discover
the model-storage model.

For convenience, we've wrapped these introspection queries into stored
procedures parameterized by the catalog version timestamp.

	-- raw introspection example w/o history awareness
    SELECT * FROM _ermrest.known_tables;
	
	-- equivalent introspection example w/ history awareness
	SELECT * FROM _ermrest.known_tables(V1::timestamptz);
	
### Special-case Handling of JSON

The preceding example to query a user data history table is sufficient
for basic column types like integers, text, and
numbers. Unfortunately, the PostgreSQL JSON support has some
asymmetries and requires special case handling of those columns. We
can pack them into the `rowdata` JSON blobs using a generic method in
our history-tracking trigger functions, but we must unpack them
differently:

    SELECT
	  t."RID" AS "RID",
	  d."Cx" AS "RCT",
	  lower(t.during) AS "RMT",
	  d."Cy" AS "RMT",
	  t."RMB",
	  d."C1" AS "Column name 1",
	  t.rowdata->"C2" AS "Column name 2", -- json or jsonb column extraction
	  ...
	  d."Ck" AS "Column name k"
	FROM _ermrest_history.tT1 t,
	LATERAL jsonb_to_record(t.rowdata) d("C1" type1, "C3" type3, ... "Ck" typek)
	WHERE t.during @> V1::timestamptz;

This example differs only in the extraction of the `C2` field. The
`jsonb_to_record()` procedure would fail to round-trip the JSON
value. Instead, we explicitly project that value directly from the raw
`rowdata` blob while using the procedure to structure the other
non-JSON values.

## Limitations

### Absence of History Tracking

The new codebase is designed assuming we will have enforced presence
of system columns.  The history-collection mechanism cannot function
on tables lacking the system columns `RID`, `RMT`, and `RMB` since our
generic data-handling functions depend on them.  If we allow
enforcement of system columns to be optional, we need to disable
history tracking for those tables.

Similarly, historical tuples are not available for SQL views even if
the view does contain system columns.

If we support a mixed environment due to lax enforcement or presence
of SQL views, some entity types will have history tracking and others
will not. A versioned request would need to further validate that only
history-tracking sources are included in the generated query or the
versioned request is unsatisfiable.

#### Table Functions as Historical Views?

If SQL views are too important to give up for historical queries, we
might add a new ERMrest feature to register a versioned table function
with the view. If registered, ERMrest would know that it could
substitute a function invocation for each query of the view:

    -- unversioned access to view
	SELECT * FROM "Some Schema"."Some View";
	
	-- versioned access
	SELECT * FROM "Some Schema"."Some View"(V1::timestamptz);
	
It would be the DBA's responsibility to properly define the procedure
in terms of versioned data sources, i.e. replacing raw table access in
the naive view definition with subqueries returning historical tuples
from the `_ermrest_history` schema.

Such procedures will be inherently fragile and require knowledge of
the source table models just like regular views. If the views are
allowed to evolve, we would want the registered table function to be
associated via our model augmentation tables. Then, this registration
record could in turn be history-tracked, and ERMrest could select the
correct table function to use for a particular historical access:

    -- unversioned access to view
	SELECT * FROM "Some Schema"."Some View";
	
	-- versioned access during historical era 1
	SELECT * FROM "Some Schema"."Some View.1"(V1::timestamptz);

    -- versioned access during historical era 2
	SELECT * FROM "Some Schema"."Some View.2"(V1::timestamptz);
	
### Inability to Revise History

Having access to historical data structured by a historical model may
be dangerous. These issues need to be addressed before this feature
can be considered production-ready:

1. If data were accidentally added to the catalog, deleting it will no
   longer expunge the data. Someone could keep querying the historical
   interface and continue to expose the data. We will need a way to
   amend historical tuples, irrevocably removing values from the
   archive.
2. If `select` ACLs were incorrectly configured on the catalog,
   adjusting them will no longer close off the information
   leak. Someone could keep querying the historical interface and
   continue to exploit the broken ACL. We will need a way to adjust
   historical ACLs, irrevocably changing how historical data queries
   will respond to some clients.
3. If a catalog has too much churn, historical tuple storage may
   become too large. We may need a way to prune history, irrevocably
   reclaiming storage.
   
If any of these changes to history are allowed, we need to solve 
further problems:

1. Version-of-version tracking for ETag/cache invalidation use cases.
2. Tombstones to signal inability to satisfy history request?
3. Determinism to allow end-to-end validation of responses,
   i.e. repeatable serialization that will pass same checksum if
   querying the same URL?