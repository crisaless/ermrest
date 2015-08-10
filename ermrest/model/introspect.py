# 
# Copyright 2013-2015 University of Southern California
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
A database introspection layer.

At present, the capabilities of this module are limited to introspection of an 
existing database model. This module does not attempt to capture all of the 
details that could be found in an entity-relationship model or in the standard 
information_schema of a relational database. It represents the model as 
needed by other modules of the ermrest project.
"""

import web

from .. import exception
from ..util import table_exists, view_exists
from .misc import frozendict, Model, Schema
from .type import Type, ArrayType, canonicalize_column_type
from .column import Column
from .table import Table
from .key import Unique, ForeignKey, KeyReference

def introspect(cur, config=None):
    """Introspects a Catalog (i.e., a database).
    
    This function (currently) does not attempt to catch any database 
    (or other) exceptions.
    
    The 'conn' parameter must be an open connection to a database.
    
    Returns the introspected Model instance.
    """
    
    # this postgres-specific code borrows bits from its information_schema view definitions
    # but is trimmed down to be a cheaper query to execute

    # Select all schemas from database, excluding system schemas
    SELECT_SCHEMAS = '''
SELECT
  current_database() AS catalog_name,
  nc.nspname AS schema_name
FROM 
  pg_catalog.pg_namespace nc
WHERE
  nc.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND NOT pg_is_other_temp_schema(nc.oid);
    '''

    # Select all column metadata from database, excluding system schemas
    SELECT_TABLES = '''
SELECT
  current_database() AS table_catalog,
  nc.nspname AS table_schema,
  c.relname AS table_name,
  c.relkind AS table_kind,
  obj_description(c.oid) AS table_comment
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace nc ON (c.relnamespace = nc.oid)
LEFT JOIN pg_catalog.pg_attribute a ON (a.attrelid = c.oid)
WHERE nc.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
  AND NOT pg_is_other_temp_schema(nc.oid) 
  AND (c.relkind = ANY (ARRAY['r'::"char", 'v'::"char", 'f'::"char", 'm'::"char"]))
  AND (pg_has_role(c.relowner, 'USAGE'::text) OR has_column_privilege(c.oid, a.attnum, 'SELECT, INSERT, UPDATE, REFERENCES'::text))
GROUP BY nc.nspname, c.relname, c.relkind, c.oid
    '''
    
    SELECT_COLUMNS = '''
SELECT
  current_database() AS table_catalog,
  nc.nspname AS table_schema,
  c.relname AS table_name,
  c.relkind AS table_kind,
  obj_description(c.oid) AS table_comment,
  array_agg(a.attname::text ORDER BY a.attnum) AS column_names,
  array_agg(pg_get_expr(ad.adbin, ad.adrelid)::text ORDER BY a.attnum) AS default_values,
  array_agg(
    CASE
      WHEN t.typtype = 'd'::"char" THEN
        CASE
          WHEN bt.typelem <> 0::oid AND bt.typlen = (-1) THEN 'ARRAY'::text
          WHEN nbt.nspname = 'pg_catalog'::name THEN format_type(t.typbasetype, NULL::integer)
          ELSE 'USER-DEFINED'::text
        END
      ELSE
        CASE
          WHEN t.typelem <> 0::oid AND t.typlen = (-1) THEN 'ARRAY'::text
          WHEN nt.nspname = 'pg_catalog'::name THEN format_type(a.atttypid, NULL::integer)
          ELSE 'USER-DEFINED'::text
        END
    END::text
    ORDER BY a.attnum) AS data_types,
  array_agg(
    CASE
      WHEN t.typtype = 'd'::"char" THEN
        CASE
          WHEN bt.typelem <> 0::oid AND bt.typlen = (-1) THEN format_type(bt.typelem, NULL::integer)
          WHEN nbt.nspname = 'pg_catalog'::name THEN NULL
          ELSE 'USER-DEFINED'::text
        END
      ELSE
        CASE
          WHEN t.typelem <> 0::oid AND t.typlen = (-1) THEN format_type(t.typelem, NULL::integer)
          WHEN nt.nspname = 'pg_catalog'::name THEN NULL
          ELSE 'USER-DEFINED'::text
        END
    END::text
    ORDER BY a.attnum) AS element_types,
  array_agg(
    col_description(c.oid, a.attnum)
    ORDER BY a.attnum) AS comments
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON (a.attrelid = c.oid)
JOIN pg_catalog.pg_namespace nc ON (c.relnamespace = nc.oid)
LEFT JOIN pg_catalog.pg_attrdef ad ON (a.attrelid = ad.adrelid AND a.attnum = ad.adnum)
JOIN pg_catalog.pg_type t ON (t.oid = a.atttypid)
JOIN pg_catalog.pg_namespace nt ON (t.typnamespace = nt.oid)
LEFT JOIN pg_catalog.pg_type bt ON (t.typtype = 'd'::"char" AND t.typbasetype = bt.oid)
LEFT JOIN pg_catalog.pg_namespace nbt ON (bt.typnamespace = nbt.oid)
WHERE nc.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
  AND NOT pg_is_other_temp_schema(nc.oid) 
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND (c.relkind = ANY (ARRAY['r'::"char", 'v'::"char", 'f'::"char", 'm'::"char"]))
  AND (pg_has_role(c.relowner, 'USAGE'::text) OR has_column_privilege(c.oid, a.attnum, 'SELECT, INSERT, UPDATE, REFERENCES'::text))
GROUP BY nc.nspname, c.relname, c.relkind, c.oid
    '''
    
    # Select the unique or primary key columns
    PKEY_COLUMNS = '''
SELECT
   k_c_u.constraint_schema,
   k_c_u.constraint_name,
   k_c_u.table_schema,
   k_c_u.table_name,
   array_agg(k_c_u.column_name::text) AS column_names
FROM information_schema.key_column_usage AS k_c_u
JOIN information_schema.table_constraints AS t_c
ON k_c_u.constraint_schema = t_c.constraint_schema
   AND k_c_u.constraint_name = t_c.constraint_name 
WHERE t_c.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
GROUP BY 
   k_c_u.constraint_schema, k_c_u.constraint_name,
   k_c_u.table_schema, k_c_u.table_name
;
    '''

    # Select the foreign key reference columns
    FKEY_COLUMNS = '''
  SELECT
    ncon.nspname::information_schema.sql_identifier AS fk_constraint_schema,
    con.conname::information_schema.sql_identifier AS fk_constraint_name,
    nfk.nspname::information_schema.sql_identifier AS fk_table_schema,
    fkcl.relname::information_schema.sql_identifier AS fk_table_name,
    (SELECT array_agg(fka.attname ORDER BY i.i)
     FROM generate_subscripts(con.conkey, 1) i
     JOIN pg_catalog.pg_attribute fka ON con.conrelid = fka.attrelid AND con.conkey[i.i] = fka.attnum
    ) AS fk_column_names,
    nk.nspname::information_schema.sql_identifier AS uq_table_schema,
    kcl.relname::information_schema.sql_identifier AS uq_table_name,
    (SELECT array_agg(ka.attname ORDER BY i.i)
     FROM generate_subscripts(con.confkey, 1) i
     JOIN pg_catalog.pg_attribute ka ON con.confrelid = ka.attrelid AND con.confkey[i.i] = ka.attnum
    ) AS uq_column_names,
    CASE con.confdeltype
            WHEN 'c'::"char" THEN 'CASCADE'::text
            WHEN 'n'::"char" THEN 'SET NULL'::text
            WHEN 'd'::"char" THEN 'SET DEFAULT'::text
            WHEN 'r'::"char" THEN 'RESTRICT'::text
            WHEN 'a'::"char" THEN 'NO ACTION'::text
            ELSE NULL::text
    END::information_schema.character_data AS rc_delete_rule,
    CASE con.confupdtype
            WHEN 'c'::"char" THEN 'CASCADE'::text
            WHEN 'n'::"char" THEN 'SET NULL'::text
            WHEN 'd'::"char" THEN 'SET DEFAULT'::text
            WHEN 'r'::"char" THEN 'RESTRICT'::text
            WHEN 'a'::"char" THEN 'NO ACTION'::text
            ELSE NULL::text
    END::information_schema.character_data AS rc_update_rule
  FROM pg_namespace ncon
  JOIN pg_constraint con ON ncon.oid = con.connamespace
  JOIN pg_class fkcl ON con.conrelid = fkcl.oid AND con.contype = 'f'::"char"
  JOIN pg_class kcl ON con.confrelid = kcl.oid AND con.contype = 'f'::"char"
  JOIN pg_namespace nfk ON fkcl.relnamespace = nfk.oid
  JOIN pg_namespace nk ON kcl.relnamespace = nk.oid
  WHERE (pg_has_role(kcl.relowner, 'USAGE'::text) 
         OR has_table_privilege(kcl.oid, 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'::text) OR has_any_column_privilege(kcl.oid, 'INSERT, UPDATE, REFERENCES'::text))
    AND (pg_has_role(fkcl.relowner, 'USAGE'::text) 
         OR has_table_privilege(fkcl.oid, 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'::text) OR has_any_column_privilege(fkcl.oid, 'INSERT, UPDATE, REFERENCES'::text))
 ;
'''

    TABLE_ANNOTATIONS = """
SELECT
  schema_name,
  table_name,
  annotation_uri,
  annotation_value
FROM _ermrest.model_table_annotation
;
"""

    COLUMN_ANNOTATIONS = """
SELECT
  schema_name,
  table_name,
  column_name,
  annotation_uri,
  annotation_value
FROM _ermrest.model_column_annotation
;
"""

    KEYREF_ANNOTATIONS = """
SELECT
  from_schema_name,
  from_table_name,
  from_column_names,
  to_schema_name,
  to_table_name,
  to_column_names,
  annotation_uri,
  annotation_value
FROM _ermrest.model_keyref_annotation
"""

    # PostgreSQL denotes array types with the string 'ARRAY'
    ARRAY_TYPE = 'ARRAY'
    
    # Dicts for quick lookup
    schemas  = dict()
    tables   = dict()
    columns  = dict()
    pkeys    = dict()
    fkeys    = dict()
    fkeyrefs = dict()

    model = Model()
    
    #
    # Introspect schemas, tables, columns
    #
    
    # get schemas (including empty ones)
    cur.execute(SELECT_SCHEMAS);
    for dname, sname in cur:
        if (dname, sname) not in schemas:
            schemas[(dname, sname)] = Schema(model, sname)

    # get columns
    cur.execute(SELECT_COLUMNS)
    for dname, sname, tname, tkind, tcomment, cnames, default_values, data_types, element_types, comments in cur:

        cols = []
        for i in range(0, len(cnames)):
            # Determine base type
            is_array = (data_types[i] == ARRAY_TYPE)
            if is_array:
                base_type = ArrayType(Type(canonicalize_column_type(element_types[i], default_values[i], config, True)))
            else:
                base_type = Type(canonicalize_column_type(data_types[i], default_values[i], config, True))
        
            # Translate default_value
            try:
                default_value = base_type.default_value(default_values[i])
            except ValueError:
                # TODO: raise informative exception instead of masking error
                default_value = None

            col = Column(cnames[i].decode('utf8'), i, base_type, default_value, comments[i])
            cols.append( col )
            columns[(dname, sname, tname, cnames[i])] = col
        
        # Build up the model as we go without redundancy
        if (dname, sname) not in schemas:
            schemas[(dname, sname)] = Schema(model, sname)
        assert (dname, sname, tname) not in tables
        tables[(dname, sname, tname)] = Table(schemas[(dname, sname)], tname, cols, tkind, tcomment)

    # also get empty tables
    cur.execute(SELECT_TABLES)
    for dname, sname, tname, tkind, tcomment in cur:
        if (dname, sname) not in schemas:
            schemas[(dname, sname)] = Schema(model, sname)
        if (dname, sname, tname) not in tables:
            tables[(dname, sname, tname)] = Table(schemas[(dname, sname)], tname, [], tkind, tcomment)

    #
    # Introspect uniques / primary key references, aggregated by constraint
    #
    cur.execute(PKEY_COLUMNS)
    for pk_schema, pk_name, pk_table_schema, pk_table_name, pk_column_names in cur:

        pk_constraint_key = (pk_schema, pk_name)

        pk_cols = [ columns[(dname, pk_table_schema, pk_table_name, pk_column_name)]
                    for pk_column_name in pk_column_names ]

        pk_colset = frozenset(pk_cols)

        # each constraint implies a pkey but might be duplicate
        if pk_colset not in pkeys:
            pkeys[pk_colset] = Unique(pk_colset, (pk_schema, pk_name) )
        else:
            pkeys[pk_colset].constraint_names.add( (pk_schema, pk_name) )

    #
    # Introspect foreign keys references, aggregated by reference constraint
    #
    cur.execute(FKEY_COLUMNS)
    for fk_schema, fk_name, fk_table_schema, fk_table_name, fk_column_names, \
            uq_table_schema, uq_table_name, uq_column_names, on_delete, on_update \
            in cur:

        fk_constraint_key = (fk_schema, fk_name)

        fk_cols = [ columns[(dname, fk_table_schema, fk_table_name, fk_column_names[i])]
                    for i in range(0, len(fk_column_names)) ]
        pk_cols = [ columns[(dname, uq_table_schema, uq_table_name, uq_column_names[i])]
                    for i in range(0, len(uq_column_names)) ]

        fk_colset = frozenset(fk_cols)
        pk_colset = frozenset(pk_cols)
        fk_ref_map = frozendict(dict([ (fk_cols[i], pk_cols[i]) for i in range(0, len(fk_cols)) ]))

        # each reference constraint implies a foreign key but might be duplicate
        if fk_colset not in fkeys:
            fkeys[fk_colset] = ForeignKey(fk_colset)

        fk = fkeys[fk_colset]
        pk = pkeys[pk_colset]

        # each reference constraint implies a foreign key reference but might be duplicate
        if fk_ref_map not in fk.references:
            fk.references[fk_ref_map] = KeyReference(fk, pk, fk_ref_map, on_delete, on_update, (fk_schema, fk_name) )
        else:
            fk.references[fk_ref_map].constraint_names.add( (fk_schema, fk_name) )

    #
    # Introspect ERMrest model overlay annotations
    #
    if table_exists(cur, '_ermrest', 'model_table_annotation'):
        cur.execute(TABLE_ANNOTATIONS)
        for sname, tname, auri, value in cur:
            try:
                table = model.schemas[sname].tables[tname]
                table.annotations[auri] = value
            except exception.ConflictModel:
                # TODO: prune orphaned annotation?
                pass

    if table_exists(cur, '_ermrest', 'model_column_annotation'):
        cur.execute(COLUMN_ANNOTATIONS)
        for sname, tname, cname, auri, value in cur:
            try:
                column = model.schemas[sname].tables[tname].columns[cname]
                column.annotations[auri] = value
            except exception.ConflictModel:
                # TODO: prune orphaned annotation?
                pass        

    if table_exists(cur, '_ermrest', 'model_keyref_annotation'):
        cur.execute(KEYREF_ANNOTATIONS)
        for from_sname, from_tname, from_cnames, to_sname, to_tname, to_cnames, auri, value in cur:
            try:
                from_table = model.schemas[from_sname].tables[from_tname]
                to_table = model.schemas[to_sname].tables[to_tname]
                refmap = frozendict({
                    from_table.columns[from_cname]: to_table.columns[to_cname]
                    for from_cname, to_cname in zip(from_cnames, to_cnames)
                })
                fkr = fkt.fkeys[frozenset(refmap.keys())].references[refmap]
                fkr.annotations[auri] = value
            except exception.ConflictModel:
                # TODO: prune orphaned annotation?
                pass        

    # save our private schema in case we want to unhide it later...
    model.ermrest_schema = model.schemas['_ermrest']
    del model.schemas['_ermrest']
    
    if not table_exists(cur, '_ermrest', 'valuemap'):
        # rebuild missing table and add it to model manually since we already introspected
        web.debug('NOTICE: adding empty valuemap during model introspection')
        model.recreate_value_map(cur.connection, cur, empty=True)
        valuemap_columns = ['schema', 'table', 'column', 'value']
        for i in range(len(valuemap_columns)):
            valuemap_columns[i] = Column(valuemap_columns[i], i, Type(canonicalize_column_type('text', 'NULL', config, True)), None)
        model.ermrest_schema.tables['valuemap'] = Table(model.ermrest_schema, 'valuemap', valuemap_columns, 't')

    return model

