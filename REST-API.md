# ERMrest API

[ERMrest](http://example.com/TBD) (rhymes with "earn rest") is a
general relational data storage service for web-based, data-oriented
collaboration.  See the [ERMrest overview] (README.md) for a general
description and motivation.

This technical document specifies the web service protocol in terms of
resources, resource representations, resource naming, and operations.

## URL Conventions

Any ERMrest URL is a valid HTTP URL and contains user-generated
content which may need to be escaped. Several reserved characters from
RFC 3986 are used as meta-syntax in ERMrest and MUST be escaped if
they are meant to be part of a user-generated identifiers or literal
data and MUST NOT be escaped if they are meant to indicate the ERMrest
meta-syntax:

- The `/` or forward-slash, used as a path separator character
- The `:` or colon, used as a separator and in multi-character tokens
- The `;` or semi-colon, used as a separator
- The `,` or comma, used as a separator
- The `=` or equals sign, used as an operator and as part of multi-character tokens
- The `?` or question-mark, used to separate a resource name from query-parameters
- The `&` or ampersand, used as a separator
- The `(` and `)` parentheses, used for nested grouping
- TODO: more syntax to list here

All other reserved characters should be escaped in user-generated
content in URLs, but have no special meaning to ERMrest when appearing
in unescaped form.

## Resource and Service Model

At its core, ERMrest is a multi-tenant service that can host multiple
datasets, each with its own entity-relationship model.  The dataset,
model, and data are further decomposed into web resources to allow
collaborative management and interaction with the data store.

### Graph of Web Resources

The ERMrest web service model exposes resources to support management
of datasets, the entity-relationship model, and the actual data stored
using that model:

1. Service: the entire multi-tenant service end-point
1. Catalog: a particular dataset (in one service)
1. Schema or model resources
  1. Schema: a particular named subset of a dataset (in one catalog)
    1. Table definition: a particular named set of data tuples (in one schema)
      1. Table comment: human-readable documentation for a table
      1. Table annotation: machine-readable documentation for a table
      1. Column definition: a particular named field of data tuples (in one table)
        1. Column comment: human-readable documentation for a column
        1. Column annotation: machine-readable documentation for a column
      1. Key definition: a particular set of columns uniquely identifying tuples (in one table)
      1. Foreign key definition: a particular set of columns... (in one table)
        1. Reference: ...linked to a set of key columns (in another table)
1. Data resources
  1. Entity: a set of data tuples corresponding to a (possibly filtered) table
  1. Attribute: a set of data tuples corresponding to a (possibly filtered) projection of a table
  1. Attribute group: a set of data tuples corresponding to a (possibly filtered) projection of a table grouped by group keys
  1. Aggregate: a data tuple summarizing a (possibly filtered) projection of a table

Rather than treating data resources as nested sub-resources of the
model resources, ERMrest treats them as separate parallel resource
spaces often thought of as separate APIs for model and data-level
access.  The reality is that these resources have many possible
semantic relationships in the form of a more general graph structure,
and any attempt to normalize them into a hierarchical structure must
emphasize some relationships at the detriment of others.  We group
model elements hierarchically to assist in listing and to emphasize
their nested lifecycle properties.  We split out data resources
because they can have a more complex relationship to multiple model
elements simultaneously.

### Model Annotations

The machine-readable annotation mechanism in ERMrest enables a
three-level interpretation of datasets:

1. The tabular data itself, which can be processed by any client capable of understanding tabular data representations.
1. The relational meta-model describing the structure of the tabular data, which can be processed by or adapted for any client capable of introspecting on relational data structures.
1. Semantic or presentation guidance, which can be processed by a client capable of augmenting the structural schemata with additional hints.

As an openly extensible, machine-readable interface, the annotations
are keyed by globally unique identifiers (URIs) and contain arbitrary
document content which can be understood according to rules associated
with that key URI.  A client SHOULD ignore annotations stored using a
key that the client does not understand.  A client MAY ignore all
annotations and simply work with the underlying relational data based
on its inherent structure with or without any additional contextual
knowledge to guide its interpretation.

### RESTful Operations Overview

The ERMrest interface supports typical HTTP operations to manage these
different levels of resource:

1. Listing, retrieval, creation, deletion of catalogs
1. Listing, retrieval, creation, deletion of model elements (schema, table, column, key, foreign-key, comment, annotation)
1. Retrieval, creation, update, deletion of tabular data
  1. Retrieval (entity, attribute, attribute group, aggregate)
  1. Creation (entity)
  1. Update (entity, attribute group)
  1. Delete (entity, attribute)

These operations produce and/or consume representations of the
resources. ERMrest defines its own JSON representations for catalog
and model elements, and supports common representations of tabular
data.

### Set-based Data Resources and Representations

ERMrest presents a composite resource model for data as sets of
tuples. Using different resource naming mechanisms, this allows
reference to data at different granularities and levels of
abstraction:

1. All entities in one table, or a filtered subset of those entities.
1. A projection of attributes for all entities in one table or a filtered subset of those entities, possibly including additional attributes joined from other tables.
1. A projection of attributes for all entities in one table or a filtered subset of those entities, grouped by grouping keys, possibly including additional attributes joined from other tables and possibly including computed aggregates over members of each group.
1. One entity (known by its key value).
1. A projection of one entity.
1. A projection of computed aggregates over all entities in one table or over a filtered subset of those entities.

For simplicity, ERMrest always uses data formats capable of
representing a set of tuples, even if the particular named data
resource is a degenerate case with set cardinality of one (single
tuple) or zero (emtpy set). The currently supported MIME types for
tabular data are:

- `application/json`: a JSON array of objects where each object represents one tuple with named fields (the default representation). 
- `text/csv`: a comma-separated value table where each row represents one tuple and a header row specifies the field names.
- `application/x-json-stream`: a stream of JSON objects, one per line, where each object represents one tuple with named fields.

Other data formats may be supported in future revisions.

### Data Resource Naming

Unlike general web architecture, ERMrest expects clients to understand
the path notation and permits (or even encourages) reflection on URL
content to understand how one data resource name relates to another.
The ERMrest data names always have a common structure:

- _service_ `/catalog/` _cid_ `/` _api_ `/` _path_
- _service_ `/catalog/` _cid_ `/` _api_ `/` _path_ _suffix_
- _service_ `/catalog/` _cid_ `/` _api_ `/` _path_ _suffix_ `?` _query parameters_
    
where the components in this structure are:

- _service_: the ERMrest service endpoint such as `https://www.example.com/ermrest`.
- _cid_: the catalog identifier for one dataset such as `42`.
- _api_: the API or data resource space identifier such as `entity`, `attribute`, `attributegroup`, or `aggregate`.
- _path_: the data path which identifies one filtered entity set with optional joined context.
- _suffix_: additional content that depends on the _api_
  - the group keys associated with `attributegroup` resources
  - the projection associated with `attribute`, `attributegroup`, and `aggregate` resources
- _query parameters_: optional parameters which may affect interpretation of the data name

#### Entity Names

The `entity` resource space denotes whole entities using names of the form:

- _service_ `/catalog/` _cid_ `/entity/` _path_

The primary naming convention, without query parameters, denotes the
final entity set referenced by _path_, as per the data path rules
described below. The denoted entity set has the same tuple structure
as the final table instance in _path_ and may be a subset of the
entities based on joining and filtering criteria encoded in
_path_. The set of resulting tuples are distinct according to the key
definitions of that table instance, i.e. any joins in the path may be
used to filter out rows but do not cause duplicate rows.

#### Attribute Names

The `attribute` resource space denotes projected attributes of
entities using names of the form:

- _service_ `/catalog/` _cid_ `/attribute/` _path_ `/` _column reference_ `,` ...

The _path_ is interpreted identically to the `entity` resource
space. However, rather than denoting a set of whole entities, the
`attribute` resource space denotes specific fields *projected* from
that set of entities.  The projected _column reference_ list elements
can be in one of two forms:

- _column name_
  - A field is projected from the final table instance of _path_
- _alias_ `:` _column name_
  - A field is projected from a table instance bound to _alias_ in _path_.
  
Like in the `entity` resource space, joined tables may cause filtering
but not duplication of rows in the final entity set. Thus, when
projecting fields from aliased table instances in _path_, values are
arbitrarily selected from one of the joined contextual rows if more
than one such row was joined to the same final entity.

#### Aggregate Names

The `aggregate` resource space denotes computed (global) aggregates
using names of the form:

- _service_ `/catalog/` _cid_ `/aggregate/` _path_ `/` _aggregate_ `,` ...

The _path_ is interpreted identically to the `attribute` resource
space. However, rather than denoting a set of whole entities, the
`aggregate` resource space denotes a single aggregated result computed
over that set. The computed _aggregate_ list elements can be in one of
several forms:

- _out alias_ `:=` _function_ `(` _column name_ `)`
- _out alias_ `:=` _function_ `(*)`
- _out alias_ `:=` _function_ `(` _in alias_ `:` _column name_ `)`
- _out alias_ `:=` _function_ `(` _in alias_ `:*)`

The _out alias_ is the name given to the computed field. The
_function_ is one of a limited set of aggregate functions supported by
ERMrest:

  - `min`: the minimum non-NULL value (or NULL)
  - `max`: the maximum non-NULL value (or NULL)
  - `cnt_d`: the count of distinct non-NULL values
  - `cnt`: the count of non-NULL values
  - `array`: an array containing all values (including NULL)

These aggregate functions are evaluated over the set of values
projected from the entity set denoted by _path_. The same column
resolution rules apply as in other projection lists: a bare _column
name_ MUST reference a column of the final entity set while an
alias-qualified column name MUST reference a column of a table
instance bound to _alias_ in the _path_.

As a special case, the psuedo-column `*` can be used in several idiomatic forms:

  - `cnt(*)`: a count of entities rather than of non-NULL values is computed
  - `array(`_alias_`:*)`: an array of records rather than an array of values is computed

TODO: document other variants?

### Data Paths

ERMrest introduces a general path-based syntax for naming data
resources with idioms for navigation and filtering of entity sets.
The _path_ element of the data resource name always denotes a set of
entities or joined entities.  The path must be interpreted from left
to right in order to understand its meaning. The denoted entity set is
understood upon reaching the right-most element of the path and may be
modified by the resource space or _api_ under which the path occurs.

#### Path Root

A path always starts with a direct table reference:

- _table name_
- _schema name_ `:` _table name_

which must already be defined in the catalog under the corresponding
model resource:

- `/schema/` _schema name_ `/table/` _table name_

The unqualified _table name_ MAY be used in a path if it is the only
occurrence of that table name across all schemata in the catalog,
i.e. only if it is unambiguous.

A path consisting of only one table reference denotes the entities
within that table.

#### Path Filters

A filter element can augment a path with a filter expression:

- _parent path_ `/` _filter_

after which the combined path denotes a filtered subset of the
entities denoted by _parent path_ where the _filter_ evaluates to a
true value.  The filter expression language is specified later in this
document. The accumulative affect of several filter path elements is a
logical conjunction of all the filtering criteria in those elements.

#### Entity Link

An entity link element can augment a path with an additional related
or joined table:

- _parent path_ `/` _table name_
- _parent path_ `/` _schema name_ `:` _table name_

as in the path root, _table name_ may be explicitly schema qualified
or left unqualified if it is unambiguous within the catalog. In order
for this basic table link element to be valid, there must be an
unambiguous foreign-key relationship linking the entity set denoted by
_parent path_ and the table denoted by _table name_. The link may
point in either direction, i.e. the _parent path_ entity set may
contain foreign keys which reference _table name_ or _table name_ may
contain foreign keys which reference the _parent path_ entities.

When there are multiple possible linkages to choose from, such a basic
entity link element is ambiguous. In these cases, a more precise
entity link element can identify an endpoint of the linkage as a set
of columns:

- _parent path_ `/(` _column name_, ... `)`
- _parent path_ `/(` _table name_ `:` _column name_, ... `)`
- _parent path_ `/(` _schema name_ `:` _table name_ `:` _column name_, ... `)`

This set of columns MUST comprise either a primary key or a foreign
key which unambiguously identifies a single possible linkage between
the _parent path_ and a single possible linked entity table.  The
resolution procedure for these column sets is as follows:

1. Column resolution:
  1. Each bare _column name_ MUST be a column of the entity set denoted by _parent path_;
  1. Each qualified name pair _table name_ `:` _column name_ MUST be a column in a table instance within _parent path_ if _table name_ is bound as an alias in _parent path_ (see following sub-section on table instance aliases);
  1. Each qualified name pair _table name_ `:` _column name_ MUST be a column in a table known unambiguously by _table name_ if _table name_ is not bound as an alias in _parent path_;
  1. Each qualified name triple _schema name_ `:` _table name_ `:` _column name_ MUST be a column within a table in the catalog.
1. Endpoint resolution:
  1. All columns in the column set MUST resolve to the same table in the catalog or the same table instance in the _parent path_;
  1. The set of columns MUST comprise either a foreign key or a key in their containing table but not both.
1. Link resolution:
  1. If the endpoint is a key or foreign key in a table in the catalog, that endpoint MUST unambiguously participate in exactly one link between that table and the entity set denoted by _parent path_;
  1. If the endpoint is a key or foreign key of a table instance in _parent path_ (whether referenced by alias-qualified or unqualified column names), that endpoint MUST unambiguously participate in exactly one link between that table instance and exactly one table in the catalog.
  
The path extended with an entity link element denotes the entities of
a new table drawn from the catalog and joined to the existing entities
in _parent path_, with the default entity context of the extended path
being the newly joined (i.e. right-most) table instance.

#### Table Instance Aliases

The root element or an entity link element may be decorated with an
alias prefix:

- _alias_ `:=` _table name_
- _parent path_ `/` _alias_ `:=` _table name_
- _parent path_ `/` _alias_ `:=(` _column name_, ... `)`

This denotes the same entity set as the plain element but also binds
the _alias_ as a way to reference a particular table instance from
other path elements to the right of the alias binding. All aliases
bound in a single path must be distinct. The alias can form a
convenient short-hand to avoid repeating long table names, and also
enables expression of more complex concepts not otherwise possible.

#### Path Context Reset

A path can be modified by resetting its denoted entity context:

- _parent path_ `/$` _alias_

where _alias name_ MUST be a table instance alias already bound by an
element within _parent path_.

This has no effect on the overall joining structure nor filtering of
the _parent path_ but changes the denoted entity set to be that of the
aliased table instance. It also changes the column resolution logic to
attempt to resolve unqualified column names within the aliased table
instance rather than right-most entity link element within _parent
path_.

A path can chain a number of entity link elements from left to right
to form long, linear joining structures. With the use of path context
resets, a path can also form tree-shaped joining structures,
i.e. multiple chains of links off a single ancestor table instance
within the _parent path_.  It can also be used to "invert" a tree to
have several joined structures augmenting the final entity set denoted
by the whole path.

## REST Operations

In the following documentation and examples, the _service_ as
described in the previous section on resource naming is assumed to be
`https://www.example.com/ermrest`.

### Catalog Operations

The catalog operations form the basic dataset lifecycle of the
multi-tenant ERMrest service.

#### Catalog Creation

The POST method is used to create an empty catalog:

    POST /ermrest/catalog
    Host: www.example.com
    
On success, this request yields the new catalog identifier, e.g. `42`
in this example:

    201 Created
    Location: /ermrest/catalog/42
    Content-Type: application/json
    
    {"id": 42}

Typical error response codes include:
- 404 Not Found
- 403 Forbidden
- 401 Unauthorized

#### Catalog Retrieval

The GET method is used to get a short description of a catalog:

    GET /ermrest/catalog/42
    Host: www.example.com
    
On success, this request yields a description:

    200 OK
    Content-Type: application/json
    
    {"id": "1", ...}

Typical error response codes include:
- 404 Not Found
- 403 Forbidden
- 401 Unauthorized

#### Catalog Deletion

The DELETE method is used to delete a catalog and all its content:

    DELETE /ermrest/catalog/42
    Host: www.example.com
    
On success, this request yields a description:

    200 OK
    Content-Type: text/plain

Typical error response codes include:
- 404 Not Found
- 403 Forbidden
- 401 Unauthorized

BUG: change this to 204 No Content?

### Model Operations

The model operations configure the entity-relationship model that will
be used to structure tabular data in the catalog.  The model must be
configured before use, but it may continue to be adjusted throughout
the lifecycle of the catalog, interleaved with data operations.

TODO.

### Data Operations

The data operations manipulate tabular data structured according to
the existing entity-relationship model already configured as schemata
resources in the catalog.

In the following examples, we illustrate the use of specific data
formats. However, content negotiation allows any of the supported
tabular data formats to be used in any request or response involving
tabular data.

#### Entity Creation

The POST operation is used to create new entity records in a table,
using an entity resource data name of the form:

- _service_ `/catalog/` _cid_ `/entity/` _table name_
- _service_ `/catalog/` _cid_ `/entity/` _schema name_ `:` _table name_

In this operation, complex entity paths with filter and linked entity
elements are not allowed.  The request input includes all columns of
the table, thus supplying full entity records of data:

    POST /ermrest/catalog/42/entity/schema_name:table_name
    Host: www.example.com
    Content-Type: text/csv
    Accept: text/csv

    column1,column2
    1,foo
    2,foo
    3,bar
    4,baz

The input data MUST observe the table definition including column
names and types, uniqueness constraints for key columns, and validity
of any foreign key references. It is an error for any existing key in
the stored table to match any key in the input data, as this would
denote the creation of multiple rows with the same keys.

On success, the response is:

    200 OK
    Content-Type: text/csv

    column1,column2
    1,foo
    2,foo
    3,bar
    4,baz

Typical error response codes include:
- 400 Bad Request
- 409 Conflict
- 403 Forbidden
- 401 Unauthorized

##### Entity Creation with Defaults

The POST operation is also used to create new entity records in a
table where some values are assigned default values, using an entity
resource data name of the form:

- _service_ `/catalog/` _cid_ `/entity/` _table name_ `?defaults=` _column name_
- _service_ `/catalog/` _cid_ `/entity/` _schema name_ `:` _table name_ `?defaults=` _column name_

In this operation, complex entity paths with filter and linked entity
elements are not allowed.  The request input includes all columns of
the table, thus supplying full entity records of data:

    POST /ermrest/catalog/42/entity/schema_name:table_name?defaults=column1
    Host: www.example.com
    Content-Type: text/csv
    Accept: text/csv

    column1,column2
    1,foo
    1,bar
    1,baz
    1,bof

The input data MUST observe the table definition including column
names and types, uniqueness constraints for key columns, and validity
of any foreign key references. All columns should still be
present. However, the values for the column (or columns) named in the
`defaults` query parameter will be ignored and server-assigned values
generated instead. It is an error for any existing key in
the stored table to match any key in the input data, as this would
denote the creation of multiple rows with the same keys.

On success, the response is:

    200 OK
    Content-Type: text/csv

    column1,column2
    4,foo
    5,bar
    6,baz
    7,bof

In this example, a `serial` type used for `column1` would lead to a
sequence of serial numbers being issued for the default column.

Typical error response codes include:
- 400 Bad Request
- 409 Conflict
- 403 Forbidden
- 401 Unauthorized

#### Entity Update

The PUT operation is used to update entity records in a table,
using an entity resource data name of the form:

- _service_ `/catalog/` _cid_ `/entity/` _table name_
- _service_ `/catalog/` _cid_ `/entity/` _schema name_ `:` _table name_

In this operation, complex entity paths with filter and linked entity
elements are not allowed.  The request input includes all columns of
the table, thus supplying full entity records of data:

    POST /ermrest/catalog/42/entity/schema_name:table_name
    Host: www.example.com
    Content-Type: text/csv
    Accept: text/csv

    column1,column2
    1,foo
    2,foo
    3,bar
    4,baz

The input data MUST observe the table definition including column
names and types, uniqueness constraints for key columns, and validity
of any foreign key references. Any input row with keys matching an
existing stored row will cause an update of non-key columns to match
the input row.  Any input row with keys not matching an existing
stored row will cause creation of a new row.

On success, the response is:

    200 OK
    Content-Type: text/csv

    column1,column2
    1,foo
    2,foo
    3,bar
    4,baz

Typical error response codes include:
- 400 Bad Request
- 409 Conflict
- 403 Forbidden
- 401 Unauthorized

#### Entity Retrieval

The GET operation is used to retrieve entity records, using an entity
resource data name of the form:

- _service_ `/catalog/` _cid_ `/entity/` _path_

In this operation, complex entity paths with filter and linked entity
elements are allowed.

    GET /ermrest/catalog/42/entity/path...

On success, the response is:

    200 OK
    Content-Type: text/csv

    column1,column2
    1,foo
    2,foo
    3,bar
    4,baz

Each result row will correspond to an entity in the entity set denoted
by _path_. This will be a filtered subset of entities from the table
instance context of _path_ considering all filtering and joining
criteria.

Typical error response codes include:
- 409 Conflict
- 403 Forbidden
- 401 Unauthorized

#### Entity Deletion

The DELETE operation is used to delete entity records, using an entity
resource data name of the form:

- _service_ `/catalog/` _cid_ `/entity/` _path_

In this operation, complex entity paths with filter and linked entity
elements are allowed.

    DELETE /ermrest/catalog/42/entity/path...

On success, the response is:

    204 No Content

The result of the operation is that each of the entity records denoted
by _path_ are deleted from the catalog. This operation only (directly)
affects the right-most table instance context of _path_. Additional
joined entity context may be used to filter the set of affected rows,
but none of the contextual table instances are modified by
deletion. However, due to constraints configured in the model, it is
possible for a deletion to cause side-effects in another table,
e.g. deletion of entities with key values causing foreign key
references to those entities to also be processed by a cascading
delete or update.

Typical error response codes include:
- 409 Conflict
- 403 Forbidden
- 401 Unauthorized
