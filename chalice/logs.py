"""Module for inspecting chalice logs.

This module provides APIs for searching, interacting
with the logs generated by AWS Lambda.

"""
import datetime


class LogRetriever(object):
    def __init__(self, client, log_group_name):
        # client -> boto3.client('logs')
        self._client = client
        self._log_group_name = log_group_name

    @classmethod
    def create_from_arn(cls, client, lambda_arn):
        """Create a LogRetriever from a client and lambda arn.

        :type client: botocore.client.Logs
        :param client: A ``logs`` client.

        :type lambda_arn: str
        :param lambda_arn: The ARN of the lambda function.

        :return: An instance of ``LogRetriever``.

        """
        lambda_name = lambda_arn.split(':')[6]
        log_group_name = '/aws/lambda/%s' % lambda_name
        return cls(client, log_group_name)

    def _convert_to_datetime(self, integer_timestamp):
        return datetime.datetime.fromtimestamp(integer_timestamp / 1000.0)

    def _is_lambda_message(self, event):
        # Lambda will also inject log messages into your log streams.
        # They look like:
        # START RequestId: guid Version: $LATEST
        # END RequestId: guid
        # REPORT RequestId: guid    Duration: 0.35 ms   Billed Duration: ...

        # By default, these message are included in retrieve_logs().
        # But you can also request that retrieve_logs() filter out
        # these message so that we only include log messages generated
        # by your chalice app.
        msg = event['message'].strip()
        return msg.startswith(('START RequestId',
                               'END RequestId',
                               'REPORT RequestId'))

    def retrieve_logs(self, include_lambda_messages=True, max_entries=None):
        """Retrieve logs from a log group.

        :type include_lambda_messages: boolean
        :param include_lambda_messages: Include logs generated by the AWS
            Lambda service.  If this value is False, only chalice logs will be
            included.

        :type max_entries: int
        :param max_entries: Maximum number of log messages to include.

        :rtype: iterator
        :return: An iterator that yields event dicts.  Each event
            dict has these keys:

            * logStreamName -> (string) The name of the log stream.
            * timestamp -> (datetime.datetime) - The timestamp for the msg.
            * message -> (string) The data contained in the log event.
            * ingestionTime -> (datetime.datetime) Ingestion time of event.
            * eventId -> (string) A unique identifier for this event.
            * logShortId -> (string) Short identifier for logStreamName.

        """
        # TODO: Add support for startTime/endTime.
        paginator = self._client.get_paginator('filter_log_events')
        shown = 0
        for page in paginator.paginate(logGroupName=self._log_group_name,
                                       interleaved=True):
            events = page['events']
            for event in events:
                if not include_lambda_messages and self._is_lambda_message(event):
                    continue
                # timestamp is modeled as a 'long', so we'll
                # convert to a datetime to make it easier to use
                # in python.
                event['ingestionTime'] = self._convert_to_datetime(
                    event['ingestionTime'])
                event['timestamp'] = self._convert_to_datetime(
                    event['timestamp'])
                # logStreamName is: '2016/07/05/[id]hash'
                # We want to extract the hash portion and
                # provide a short identifier.
                identifier = event['logStreamName']
                if ']' in identifier:
                    index = identifier.find(']')
                    identifier = identifier[index+1:index+7]
                event['logShortId'] = identifier
                yield event
                shown += 1
                if max_entries is not None and shown >= max_entries:
                    return