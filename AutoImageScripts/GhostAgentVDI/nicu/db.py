"""This modules contains database related methods and classes.
"""

import pymssql
import sys
import re
import time
import sqlite3
import itertools
import logging
import threading
import uuid
import config

__all__ = [
    "init_db",
    "run_query_sql",
    "run_action_sql",
    "CommonDatabaseException",
    "SQLServerDB",
    "SQLiteDB",
    "Row"
]

LOGGER = logging.getLogger(__name__)
_DB_HOST = None
_DB_USER = None
_DB_PASSWORD = None
_DB_DATABASE = None
_DB_LOCK = threading.Lock()
_DB_LOCK_SQLSERVERDB_POOL_GET = threading.Lock()
_DB_LOCK_SQLSERVERDB_POOL_RETURN = threading.Lock()
_DB_LOCK_SQLSERVERDB = threading.Lock()

def init_db(host, user, password, database):
    """Init the database connection strings"""
    global _DB_HOST, _DB_USER, _DB_PASSWORD, _DB_DATABASE
    _DB_HOST = host
    _DB_USER = user
    _DB_PASSWORD = password
    _DB_DATABASE = database


def _get_connection(retry=False,
                    interval=5):
    """Get a pymssql connection"""
    conn = None
    # if server down, wait querying until server recover
    while conn is None:
        try:
            conn = pymssql.connect(host=_DB_HOST,
                                   user=_DB_USER,
                                   password=_DB_PASSWORD,
                                   database=_DB_DATABASE)
            break
        except Exception:
            exeinfo = sys.exc_info()
            LOGGER.error("Failed to connect host %s: %s" %
                         (_DB_HOST, str(exeinfo[1])))

            errorid_re = re.compile(r"SQL Server message (?P<id>\d+),")
            matched = errorid_re.match(str(exeinfo[1]))
            if matched and matched.group("id"):
                errorid = int(matched.group("id"))
                # 18456: Login using wrong user name or wrong password
                # 911: Login on inexistent database
                if errorid in [911, 18456]:
                    if conn:
                        conn.close()
                    return
        if retry:
            time.sleep(interval)
        else:
            break

    return conn


def run_query_sql(query, retry=False):
    """Execute a query SQL statement, and return the query result."""
    conn = None
    try:
        _DB_LOCK.acquire()
        conn = _get_connection(retry)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        conn.commit()
        return rows
    except Exception, error:
        LOGGER.error("Failed to execute query statement <%s> : %s" %
                     (query, error))
    finally:
        if conn:
            conn.close()
        _DB_LOCK.release()


def run_action_sql(query, retry=False):
    """Execute an insert/update SQL Statement."""
    conn = None
    try:
        _DB_LOCK.acquire()
        msg = []
        command_lists = []
        if (not isinstance(query, (basestring, list))):
            msg.append("The input query of function "
                       "execute is not a basic string or list.")
            raise CommonDatabaseException(msg)
        if isinstance(query, basestring):
            command_lists.append(query)
        if isinstance(query, list):
            command_lists += query

        conn = _get_connection(retry)
        cur = conn.cursor()
        for sqlitem in command_lists:
            cur.execute(sqlitem)
        conn.commit()
        return 0
    except Exception, error:
        LOGGER.error("Failed to execute action statement <%s> : %s" %
                     (query, error))
    finally:
        if conn:
            conn.close()
        _DB_LOCK.release()
    return 1


class CommonDatabaseException(Exception):
    """Custom defined database exception"""
    pass

class PymssqlConnection:
    """
    Wrapper class to hold a pymssql connection object.
    Used by the connection pool in SQLServerDB
    """


    def __init__(self, conn_id=None, conn=None, is_busy=False, pool_id=None):
        self.conn_id = conn_id
        self.conn = conn
        self.is_busy = is_busy
        self.pool_id = pool_id


class SQLServerDB:
    """
    Connect to the MS SQL Server and execute SQL statement.
    Based on pymssql module @http://pymssql.sourceforge.net/index.php
    """

    __pooldict = {}
    __last_used_username = None
    __last_used_password = None
    __last_used_host = None
    __last_used_database = None

    @staticmethod
    def connect(
                dsn=None,
                user=None,
                password=None,
                host=None,
                database=None,
                timeout=None, login_timeout=None, trusted=False,
                charset=None, as_dict=False, max_conn=None
               ):
        """
        Constructor for creating a connection to the database. Returns
        a connection object. Paremeters are as follows:

        dsn       Deprecated
        user      database user to connect as
        password  user's password
        trusted   Deprecated
        host      database host and instance
        database  the database you want initially to connect to
        timeout   Deprecated
        login_timeout
                  Deprecated
        charset   Deprecated
        as_dict   Deprecated
        max_conn  Deprecated

        Examples:
        con = SQLServerDB.connect(host="sast-saas", user='saas',
                                password='saassaas', database='SaaSMetadata')
        """

        # If user didn't specify connection string, use the last saved string.
        # If last saved string is empty, use the default ones
        user = user or SQLServerDB.__last_used_username or _DB_USER
        password = password or SQLServerDB.__last_used_password or _DB_PASSWORD
        host = host or SQLServerDB.__last_used_host or _DB_HOST
        database = database or SQLServerDB.__last_used_database or _DB_DATABASE

        # Save the last used connection string
        # if user passed null parameter, use the last used one
        SQLServerDB.__last_used_username = user
        SQLServerDB.__last_used_password = password
        SQLServerDB.__last_used_host = host
        SQLServerDB.__last_used_database = database

        try:
            _DB_LOCK_SQLSERVERDB.acquire()

            if max_conn:
                raise DeprecationWarning(
                        "The parameter max_conn had been deprecated, " \
                        "it should be configured in the config.py now.")

            if dsn or timeout or login_timeout \
                    or trusted or charset or as_dict:
                raise DeprecationWarning(
                        "The parameter dsn, timeout, login_timeout, " \
                        "trusted, and charset or as_dict had been " \
                        "deprecated.")

            pool = SQLServerDB._get_connection_pool(user, password,
                                                    database, host)
            p_conn = SQLServerDB._get_connection(pool)
            return p_conn

        finally:
            _DB_LOCK_SQLSERVERDB.release()

    @staticmethod
    def _get_connection_pool(user, password, database, host):
        """
        Get a connection pool
        If the connection pool doesn't exist, create one
        """

        key = '_'.join([host, user, password, database])
        if not key in SQLServerDB.__pooldict:
            SQLServerDB.__pooldict[key] = SQLServerDBPool(
                                                user=user, password=password,
                                                database=database, host=host)
        return SQLServerDB.__pooldict[key]

    @staticmethod
    def _get_connection(pool):
        """Get a connection from the pool."""
        # If the pool had not been initialized, initialize the pool
        p_conn = pool.get_connection()
        return p_conn


    @staticmethod
    def close(conn, close=True):
        """Close connection to the database."""
        try:
            if conn:
                SQLServerDB.__pooldict[conn[3]].return_connection(conn, close)
        except Exception, e:
            raise e


    @staticmethod
    def query(sql_statement, conn=None):
        """
        Execute query SQL statement. The SQL statement should be a string.
        """
        rows = []
        msg = []
        new_fg = False
        close_fg = False
        if not isinstance(sql_statement, basestring):
            msg.append("The input sql_statement of function "
                       "query is not a basic string.")
            raise CommonDatabaseException(msg)
        try:
            if not conn:
                new_fg = True
                conn = SQLServerDB.connect()
            cur = conn[1].cursor()
            cur.execute(sql_statement)
            rows = cur.fetchall()
            conn[1].commit()
            return rows
        except Exception, e:
            close_fg = True
            msg = []
            msg.append("Failed to execute query statement : %s" %
                       sql_statement)
            msg.append(e)
            raise CommonDatabaseException(msg)
        finally:
            if conn and (close_fg or new_fg):
                SQLServerDB.close(conn, close_fg)


    @staticmethod
    def query_one(sql_statement, conn=None):
        rows = SQLServerDB.query(sql_statement, conn)
        if not rows:
            raise Exception('No record in database.')
        return rows[0]


    @staticmethod
    def execute(sql_statements, conn=None):
        """Execute operation SQL statement. The SQL statement should
        be a string or a list of string.
        """
        command_lists = []
        msg = []
        new_fg = False
        close_fg = False
        if (not isinstance(sql_statements, basestring) and
            not isinstance(sql_statements, list)):
            msg.append("The input sql_statements of function "
                       "execute is not a basic string or list.")
            raise CommonDatabaseException(msg)
        if isinstance(sql_statements, basestring):
            command_lists.append(sql_statements)
        if isinstance(sql_statements, list):
            command_lists += sql_statements

        try:
            if not conn:
                # It's unnecessary to close this new connection after task
                # finished, since that function "SQLServerDB.connect" will
                # create a complete connection pool.
                # If we even close this connection, other connections which
                # are in the same pool will not be closed.
                new_fg = True
                conn = SQLServerDB.connect()
            cur = conn[1].cursor()
            for sql_item in command_lists:
                cur.execute(sql_item)
            conn[1].commit()
            return 0
        except Exception, e:
            # It's required to close this connection when error is raised.
            # If this connection isn't closed, other query or execute
            # operations will be blocked in underlying layer by database
            # when these operations involve some data locked by
            # this operation.
            close_fg = True
            msg = []
            msg.append("Failed to execute execute statement : %s" %
                       sql_statements)
            msg.append(e)
            raise CommonDatabaseException(msg)
        finally:
            if conn and (close_fg or new_fg):
                SQLServerDB.close(conn, close_fg)
        return 1


    @staticmethod
    def get_connection_pool_size(user=None, password=None,
                                 host=None, database=None):
        """
        Get the connection pool size of a specific pool owned by the class
        """
        user = user or SQLServerDB.__last_used_username or _DB_USER
        password = password or SQLServerDB.__last_used_password or _DB_PASSWORD
        host = host or SQLServerDB.__last_used_host or _DB_HOST
        database = database or SQLServerDB.__last_used_database or _DB_DATABASE

        # query the connection pool size should not alter the
        # last saved connection string.

        key = '_'.join([host, user, password, database])
        if key in SQLServerDB.__pooldict:
            return SQLServerDB.__pooldict[key].get_connection_pool_size()

        else:
            return 0


    @staticmethod
    def close_all_connections(no_wait=False):
        """close all connections generated by the SQLServerDB"""
        try:
            _DB_LOCK_SQLSERVERDB.acquire()

            for key in SQLServerDB.__pooldict:
                SQLServerDB.__pooldict[key].close_connection_pool(no_wait)

            SQLServerDB.__pooldict = {}

        finally:
            _DB_LOCK_SQLSERVERDB.release()


class SQLServerDBPool:
    """
    Connect to the MS SQL Server and execute SQL statement.
    Based on pymssql module @http://pymssql.sourceforge.net/index.php
    """

    def __init__(
            self, user=None, password=None,
            host=None, database=None):

        """
        Constructor for initializing a connection pool to the database.

        user      database user to connect as
        password  user's password
        host      database host and instance
        database  the database you want initially to connect to
        """
        self.__p_connections = []

        self.user = user
        self.password = password
        self.host = host
        self.database = database

        self.pool_id = '_'.join([host, user, password, database])

        self.max_conn = config.DB_POOL_DEFAULT_MAX_CONNECTION
        self.init_conn = config.DB_POOL_DEFAULT_INITIAL_CONNECTION
        self.incremental_conn = config.DB_POOL_DEFAULT_INCREMENTAL_CONNECTION

        if self.max_conn < self.init_conn:
            self.max_conn = self.init_conn

        try:
            self._create_pool()
        except Exception:
            LOGGER.exception("Failed to creat connection pool")


    def get_connection(self):
        """Returns a pymssql connection object"""
        #make sure the connection pool had been created
        if len(self.__p_connections)==0:
            return None

        try:

            _DB_LOCK_SQLSERVERDB_POOL_GET.acquire()
            p_conn = self._get_free_connection()

            while not p_conn:
                p_conn = self._get_free_connection()
                time.sleep(1)

            return p_conn

        except Exception:
            LOGGER.exception("Exception thrown when getting a free" \
                             " connection, return None")
            return None

        finally:
            _DB_LOCK_SQLSERVERDB_POOL_GET.release()



    def _new_connection(self):
        """Create a new pymssql connection"""
        conn = None
        try:
            conn = pymssql.connect(
                        self, user=self.user, password=self.password,
                        host=self.host, database=self.database)

        except Exception, e:
            msg = []
            msg.append(e)
            msg.append("Parameters : user=%s;password=%s;"
                       "host=%s;database=%s;" %
                            (self.user, self.password,
                             self.host, self.database))
            raise CommonDatabaseException(msg)
        return conn


    def _create_pool(self):
        """
        Create the connection pool
        """

        #connection pool had been created, return
        if len(self.__p_connections) > 0:
            return

        self._create_connections(self.init_conn)
        LOGGER.debug("Connection pool had been created")


    def _create_connections(self, number_of_connections=1):
        """
        Create connections and put them into the connection pool

        number_of_connections
                number of connections to be created and put into the pool
        """
        try:
            for connection in range(number_of_connections):
                if self.max_conn > 0 and \
                        len(self.__p_connections) >= self.max_conn:
                    break
                self.__p_connections.append(
                        (uuid.uuid1(), self._new_connection(),
                         False, self.pool_id))
        except Exception, e:
            raise e


    def _get_free_connection(self):
        """Get a free connection in the pool"""
        p_conn = self._find_free_connection()

        # If there's no free connection in the pool, create new connections
        if not p_conn:
            self._create_connections(self.incremental_conn)
            p_conn = self._find_free_connection()
            if not p_conn:
                return None

        return p_conn


    def _find_free_connection(self):
        """Find a free connection from the pool"""
        for index, p_conn in enumerate(self.__p_connections):
            if not p_conn[2]:
                self.__p_connections[index] = (p_conn[0], p_conn[1],
                                               True, self.pool_id)

                # Test if this connection is still useable
                if not self._test_connection(p_conn):
                    try:
                        new_conn = self._new_connection()
                        new_p_conn = (uuid.uuid1(), new_conn,
                                      True, self.pool_id)
                        self.__p_connections[index] = new_p_conn

                        return new_p_conn
                    except Exception:
                        LOGGER.error("Failed to create new connection")
                        return None

                return p_conn


    def _test_connection(self, p_conn):
        """Test if connection is available"""
        sql_command = \
            "select top 1 Machine_Info.MachineName from Machine_Info"
        try:
            SQLServerDB.query(sql_command, p_conn)

        except Exception:
            # If exception happens, try to close this connection
            # ignore exception
            try:
                self._close_connection(p_conn)
            except:
                pass

            return False

        return True


    def _close_connection(self, p_conn):
        """Close connection to the database."""
        try:
            if p_conn:
                # need to free this connection in DB pool.
                self.return_connection(p_conn, True)
        except Exception, e:
            raise e


    def close_connection_pool(self, no_wait=False):
        """Close connection pool and delete all connections"""
        try:
            #request the get lock, so that when closing connection pool,
            #there should not be new get request happening.
            _DB_LOCK_SQLSERVERDB_POOL_GET.acquire()
            # If connection pool is empty, return
            if len(self.__p_connections) <= 0:
                return

            while len(self.__p_connections) > 0:

                p_conn = self.__p_connections[0]

                # if the connection is still busy, wait 5 seconds
                if p_conn[2] and not no_wait:
                    time.sleep(5)

                self._close_connection(p_conn)

                del self.__p_connections[0]
        finally:
            _DB_LOCK_SQLSERVERDB_POOL_GET.release()


    def return_connection(self, p_conn, close=False):
        """Return a connection to the pool"""
        try:
            if close and p_conn and p_conn[1]:
                p_conn[1].close()
        except Exception:
            pass
        try:
            _DB_LOCK_SQLSERVERDB_POOL_RETURN.acquire()
            # If connection pool is empty, return
            if len(self.__p_connections) <= 0:
                return

            for index, p_conn_list in enumerate(self.__p_connections):

                # Find the index in the connection pool
                if p_conn[0] == p_conn_list[0]:
                    self.__p_connections[index] = \
                        (p_conn_list[0], p_conn_list[1], False, self.pool_id)
                    break
        finally:
            _DB_LOCK_SQLSERVERDB_POOL_RETURN.release()


    def get_connection_pool_size(self):
        """Get the connection pool size"""
        return len(self.__p_connections)


OperationalError = sqlite3.OperationalError


class SQLiteDB:
    """A lightweight wrapper around sqlite3; based on tornado.database

    db = nicu.db.SQLiteDB("filename")
    for article in db.query("SELECT * FROM articles")
        print article.title

    Cursors are hidden by the implementation.
    """

    def __init__(self, filename, isolation_level=None):
        self.filename = filename
        self.isolation_level = isolation_level  # None = autocommit
        self._db = None
        try:
            self.reconnect()
        except:
            # log error @@@
            raise

    def close(self):
        """Close database connection"""
        if getattr(self, "_db", None) is not None:
            self._db.close()
        self._db = None

    def reconnect(self):
        """Closes the existing database connection and re-opens it."""
        self.close()
        self._db = sqlite3.connect(self.filename)
        self._db.isolation_level = self.isolation_level

    def _cursor(self):
        """Returns the cursor; reconnects if disconnected."""

        if self._db is None:
            self.reconnect()
        return self._db.cursor()

    def __del__(self):
        self.close()

    def execute(self, query, *parameters):
        """
        Executes the given query, returning the lastrowid from the query.
        """

        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def executemany(self, query, parameters):
        """
        Executes the given query against all the given param sequences
        """

        cursor = self._cursor()
        try:
            cursor.executemany(query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def _execute(self, cursor, query, parameters):
        """Execute test"""

        try:
            return cursor.execute(query, parameters)
        except OperationalError:
            # log error @@@
            self.close()
            raise

    def query(self, query, *parameters):
        """Returns a row list for the given query and parameters."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            column_names = [d[0] for d in cursor.description]
            return [Row(itertools.izip(column_names, row)) for row in cursor]
        finally:
            # cursor.close()
            pass

    def get(self, query, *parameters):
        """Returns the first row returned for the given query."""
        rows = self.query(query, *parameters)
        if not rows:
            return None
        elif len(rows) > 1:
            raise Exception("Multiple rows returned from sqlite.get() query")
        else:
            return rows[0]


class Row(dict):
    """A dict that allows for object-like property access syntax."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)
