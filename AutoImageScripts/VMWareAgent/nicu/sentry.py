import os
import getpass
import socket
import logging
import logging.handlers
import platform
import sys

import raven


LOGGER = logging.getLogger(__name__)

class SentryErrorFilter(logging.Filter):
    """
    A Filter to filter record for SentryErrorHandler
    """
    def filter(self, record):
         # If this record hasn't been set with "sentry_type", ignore it.
        if not hasattr(record, 'sentry_type'):
            return False
        return True

class SentryErrorHandler(logging.Handler):
    """
    A handle to report events to sentry server

    it will configure a specified Raven client and report events
    to sentry server.
    """


    def __init__(self, dsn, **options):
        logging.Handler.__init__(self)
        #self.addFilter(SentryErrorFilter())
        
        # You can find LOG_LEVELS in sentry.constants.
        # We need map the level of logger to the one of sentry recognized
        self.LOG_LEVELS = {
            logging.DEBUG: 'debug',
            logging.INFO: 'info',
            logging.WARNING: 'warning',
            logging.ERROR: 'error',
            logging.CRITICAL: 'fatal',
            logging.FATAL: 'fatal',
        }

        o = options
        Tags = o.get('tags') or {}
        Release = o.get('release') or '1.0.0'
        User = o.get('user') or {}
        
        self.client = raven.Client(
            # by default, set time out to 10s
            dsn = dsn +"?timeout=10",
            # pass along the common tags of this application
            tags = Tags,
            # pass along the version of this application
            release = Release,
        )
        
        if User:
            # You can provide information about user,
            # e.g id, email, ip_address, username
            self.client.context.merge({"user" : User})
        else:
            # by default, get the machine information
            machine = {
                "username" : getpass.getuser(), 
                "ip_address": socket.gethostbyname(socket.gethostname())}
            self.client.context.merge({"user" : machine})
        return


    def emit(self, record):
        if record.levelno < self.level:
            return

        sentry_message = record.msg

        sentry_level = self.LOG_LEVELS[logging.DEBUG]
        if record.levelno in self.LOG_LEVELS.keys():
            sentry_level = self.LOG_LEVELS[record.levelno]

        sentry_tags = {}
        if hasattr(record, 'sentry_tags'):
            sentry_tags = record.sentry_tags

        sentry_extra = {}
        if hasattr(record, 'sentry_extra'):
            sentry_extra = record.sentry_extra

        if not hasattr(record, 'sentry_type'):
            self.client.captureMessage(
                sentry_message,
                level = sentry_level,
                tags = sentry_tags,
                extra = sentry_extra)
        elif record.sentry_type.lower() == "message":
            self.client.captureMessage(
                sentry_message,
                level = sentry_level,
                tags = sentry_tags,
                extra = sentry_extra)
        elif record.sentry_type.lower() == "exception":
            sentry_extra['Record_Message'] = sentry_message
            self.client.captureException(
                level = sentry_level,
                tags = sentry_tags,
                extra = sentry_extra)
        return
