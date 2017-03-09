"""
private functions used in cartoframes methods
"""
import pandas as pd

def get_auth_client(username=None, api_key=None, cdb_client=None):
    """Instantiates a SQL Client from the Carto Python SDK (v1.0.0)
    """
    from carto.sql import SQLClient
    from carto.auth import APIKeyAuthClient
    if cdb_client is None:
        BASEURL = 'https://{username}.carto.com/api/'.format(username=username)
        auth_client = APIKeyAuthClient(BASEURL, api_key)
        sql = SQLClient(auth_client)
    elif (username is None) and (api_key is None):
        sql = SQLClient(cdb_client)
    else:
        raise Exception("`username` and `api_key` or `cdb_client` has to be "
                        "specified.")
    return sql


def create_table_query(tablename, schema, username, is_org_user=False,
                       debug=False):
    """write a create table query from tablename and schema
        Example output:
        CREATE TABLE "interesting_birds"(location text, name text, size numeric);
        SELECT CDB_CartodbfyTable('eschbacher', 'interesting_birds');
    """

    cols = ', '.join(["{colname} {datatype}".format(colname=k,
                                                    datatype=schema[k])
                      for k in schema])
    if debug: print(cols)
    query = '''
        CREATE TABLE "{tablename}"({cols});
        SELECT CDB_CartodbfyTable('{username}', '{tablename}');
        '''.format(tablename=tablename,
                   cols=cols,
                   username=(username if is_org_user else 'public'))
    if debug: print(query)
    return query

# TODO: combine this with other datatype maps
# PostgreSQL -> pandas
def map_dtypes(pgtype):
    """
    Map PostgreSQL data types (key) to NumPy/pandas dtypes (value)
    :param pgtype: string PostgreSQL/CARTO datatype to map to pandas data type
    Output
    :param : string data type used in pandas
    """
    # may not be a complete list, could not find CARTO SQL API documentation
    # about data types
    dtypes = {'number': 'float64',
              'date': 'datetime64',
              'string': 'object',
              'geometry': 'object',
              'boolean': 'bool'}
    try:
        return dtypes[pgtype]
    except KeyError:
        # make it a string if not in dict above
        return 'object'

# pandas -> PostgreSQL
def dtype_to_pgtype(dtype, colname):
    """
    Map dataframe types to carto postgres types
    """
    if colname in ('the_geom', 'the_geom_webmercator'):
        return 'geometry'
    else:
        mapping = {'float64': 'numeric',
                   'int64': 'int',
                   'datetime64': 'date',
                   'object': 'text',
                   'bool': 'boolean'}
        try:
            return mapping[dtype]
        except KeyError:
            return 'text'

# NumPy -> PostgreSQL
def map_numpy_to_postgres(item):
    """
      Map NumPy values to PostgreSQL values
    """
    import math
    if isinstance(item, str):
        if "'" in item:
            return "'{}'".format(item.replace("'", "\'\'"))
        return "'{}'".format(item)
    elif isinstance(item, float):
        if math.isnan(item):
            return 'null'
        return str(item)
    elif item is None:
        return 'null'
    return str(item)

# PostgreSQL -> NumPy
def datatype_map(dtype):
    """
       map NumPy types to PostgreSQL types
    """
    # TODO: add datetype conversion
    if 'float' in dtype:
        return 'numeric'
    elif 'int' in dtype:
        return 'int'
    elif 'bool' in dtype:
        return 'boolean'
    else:
        return 'text'


def format_row(rowvals, dtypes):
    """

    """
    mapped_vals = []
    for idx, val in enumerate(rowvals):
        mapped_vals.append(map_numpy_to_postgres(val))
    return ','.join(mapped_vals)

def transform_schema(pgschema):
    """
    Transform schema returned via SQL API to dict for pandas
    Input:
    :param pgschema: dict The schema returned from CARTO's SQL API, in the
                     following format:
                     {'col1': {'type': 'numeric'},
                      'col2': {'type': 'date'},
                      'col3': {'type': 'numeric'},
                      ...}
    Output:
    Transformed schema data types in the following format:
    {'col1': 'float64',
     'col2': 'datetime64',
     'col3': 'float64',
     ...}
    """
    datatypes = {}
    for field in pgschema:
        if 'cartodb_id' in field:
            continue
        datatypes[field] = map_dtypes(pgschema[field]['type'])
    return datatypes

def get_username(baseurl):
    """
    Retrieve the username from the baseurl.
    :param baseurl: string Must be of format https://{username}.carto.com/api/

    NOTE: Not compatible with onprem, etc.
    """
    # TODO: make this more robust
    import re
    m = re.search('https://(.*?).carto.com/api/', baseurl)
    return m.group(1)

def get_geom_type(sql_auth_client, tablename):
    """
        Get the geometry type in tablename for storing in dataframe metadata

        :param sql_auth_client: object SQL Auth client from CARTO Python SDK
        :param tablename: string Name of table for cartoframe
    """
    geomtypes = {'ST_Point': 'point',
                 'ST_MultiPoint': 'point',
                 'ST_LineString': 'line',
                 'ST_MultiLineString': 'line',
                 'ST_Polygon': 'polygon',
                 'ST_MultiPolygon': 'polygon'}

    # NOTE: assumes one geometry type per table
    result = sql_auth_client.send('''
        SELECT ST_GeometryType(the_geom) As geomtype
        FROM "{tablename}"
        WHERE the_geom IS NOT NULL
        LIMIT 1'''.format(tablename=tablename))
    try:
        return geomtypes[result['rows'][0]['geomtype']]
    except KeyError:
        raise Exception(("Cannot create a map from `{tablename}` because this "
                        "table does not have "
                        "geometries ({geomreported})").format(
                            tablename=tablename,
                            geomreported=result['rows'][0]['geomtype']))
    except Exception as err:
        print("ERROR: {}".format(err))
    return None

# TODO: let DO augmentation code use this
def df_from_query(query, carto_sql_client, is_org_user, username,
                  tablename=None, debug=False):
    """
        Create a cartoframe or fill a pd.DataFrame with data from a CARTO
        account based on a custom query.
        :param query: string Custom query
        :param carto_sql_client: object CARTO authentication client for SQL API
        :param is_org_user: boolean Whether the user is in an organization or
                            not
        :param username: string CARTO username
    """
    if tablename:
        create_table = '''
            CREATE TABLE {tablename} As
            SELECT *
              FROM ({query}) As _wrap;
            SELECT CDB_CartodbfyTable('{org}', '{tablename}');
        '''.format(tablename=tablename,
                   query=query,
                   org='public' if is_org_user else username)
        if debug: print("Creating table: {}".format(create_table))
        resp = carto_sql_client.send(create_table)
        if debug: print(resp)
        new_tablename = resp['rows'][0]['cdb_cartodbfytable']
        table_resp = carto_sql_client.send(
            'SELECT * FROM {tablename}'.format(tablename=new_tablename))
        if debug: print(table_resp)
        schema = transform_schema(table_resp['fields'])
        return pd.DataFrame(table_resp['rows']).set_index('cartodb_id').astype(schema)
    else:
        resp = carto_sql_client.send(query)
        schema = transform_schema(resp['fields'])
        return pd.DataFrame(resp['rows']).astype(schema)

    return None


def df_from_table(query, carto_sql_client, index=None):
    """
    Create a pandas DataFrame from a CARTO table
    """
    resp = carto_sql_client.send(query)
    schema = transform_schema(resp['fields'])
    if index:
        return pd.DataFrame(resp['rows']).set_index('cartodb_id').astype(schema)
    else:
        return pd.DataFrame(resp['rows']).astype(schema)

def upsert_table(self, df_diff, n_batch=30, debug=False):

    n_items = len(df_diff)
    queries = []
    upsert_query = ' '.join(
        ("INSERT INTO \"{tablename}\"(\"cartodb_id\", \"{colname}\")",
         "VALUES ({cartodb_id}, {colval})",
         "ON CONFLICT (\"cartodb_id\")",
         "DO UPDATE SET \"{colname}\" = {colval}",
         "WHERE EXCLUDED.\"cartodb_id\" = {cartodb_id};"))
    n_batches = n_items // n_batch
    batch_num = 1
    for row_num, row in enumerate(df_diff.iteritems()):
        # if debug: print(row)
        cartodb_id = row[0][0]
        colname = row[0][1]

        # fill query template
        temp_query = upsert_query.format(
            tablename=self.get_carto_tablename(),
            colname=colname,
            colval=map_numpy_to_postgres(self.loc[cartodb_id][colname]),
            cartodb_id=cartodb_id)

        queries.append(temp_query)

        # run batch if at n_batch queries, or at last item
        if (len(queries) == n_batch) or (row_num == n_items - 1):
            batchquery = '\n'.join(queries)
            print("{curr_batch} of {n_batches}".format(
                curr_batch=batch_num,
                n_batches=n_batches))
            batch_num = batch_num + 1
            if debug: print("Num chars in batch: {}".format(len(batchquery)))
            if debug: print(batchquery)

            # send batch query to carto
            resp = self.carto_sql_client.send(batchquery)
            if debug: print(resp)

            # clear for another batch
            queries = []

    return None

# TODO: change this to be a list of colnames
def drop_col(self, colname, n_batch=30, debug=False):
    """
    Drop specified column
    """

    alter_query = '''
        ALTER TABLE "{tablename}"
        DROP COLUMN "{colname}"
    '''.format(tablename=self.get_carto_tablename(),
               colname=colname)

    if debug: print(alter_query)
    resp = self.carto_sql_client.send(alter_query)
    if debug: print(resp)
    return None


def add_col(self, colname, n_batch=30, debug=False):
    """
    Alter table by adding a column created from a DataFrame operation
    """

    if debug: print("Create new column {col}".format(col=colname))
    # Alter table add column
    #
    alter_query = '''
        ALTER TABLE "{tablename}"
        ADD COLUMN "{colname}" {datatype};
    '''.format(tablename=self.get_carto_tablename(),
               colname=colname,
               datatype=datatype_map(str(self.dtypes[colname])))
    if debug: print(alter_query)

    # add column
    resp = self.carto_sql_client.send(alter_query)
    if debug: print(resp)

    # update all the values in that column
    #
    # NOTE: fails if colval is 'inf' or some other exceptional Python
    #  or NumPy type
    n_items = len(self[colname])
    update_query = '''
        UPDATE "{tablename}"
        SET "{colname}" = {colval}
        WHERE "cartodb_id" = {cartodb_id};
    '''
    queries = []

    for row_num, item in enumerate(self[colname].iteritems()):
        # if debug: print(item)
        temp_query = update_query.format(
            tablename=self.get_carto_tablename(),
            colname=colname,
            colval=map_numpy_to_postgres(item[1]),
            cartodb_id=item[0]).strip()
        queries.append(temp_query)
        if (len(queries) == n_batch) or (row_num == n_items - 1):
            output_query = '\n'.join(queries)
            if debug: print(output_query)
            if debug: print("Num chars in query: {}".format(len(output_query)))
            resp = self.carto_sql_client.send(output_query)
            queries = []

    return None

# utilities for pandas.DataFrame.carto_map


def get_anon_mapconfig(params):
    """Anonymous Maps API template for carto.js
    :param mapconfig_params: dict with the following keys:
      - username: string username of CARTO account
      - tablename: string tablename cartoframe is associated with
      - cartocss: CartoCSS string for styling the data on the map
      - basemap: Default basemap of the data

    dtypes one of
      * quantitative: float64 (float32, int32, int64)
      * categorical: bool, object
        * cartocss rule: ramp([room_type], cartocolor(Bold), category(4))
          dtypes = {'number': 'float64',
                    'date': 'datetime64',
                    'string': 'object',
                    'geometry': 'object',
                    'boolean': 'bool'}

    color palettes: https://github.com/CartoDB/CartoColor/blob/master/cartocolor.js
    """

    if params['basemap'] is not None:
        basemap = params['basemap']
    else:
        basemap = 'https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png'
    map_args = {'cartocss': params['cartocss'],
                'basemap': basemap,
                'tablename': params['tablename'],
                'username': params['username']}

    mapconfig = '''{"user_name": "%(username)s",
                    "type": "cartodb",
                    "sublayers": [{
                      "type": "http",
                      "urlTemplate": "%(basemap)s"
                      }, {
                      "sql": "select * from %(tablename)s",
                      "cartocss": "%(cartocss)s"
                      }],
                      "subdomains": [ "a", "b", "c" ]
                      }''' % map_args
    return mapconfig
