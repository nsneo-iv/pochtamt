"""Разбор вывода postqueue -j и doveadm quota."""
import importlib.util
import os

spec = importlib.util.spec_from_file_location("mail_agent", os.path.join(os.path.dirname(__file__), "..", "mail_agent.py"))
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def test_parse_queue():
    out = ('{"queue_name":"deferred","queue_id":"4ABC123DEF","arrival_time":1700000000,"message_size":2048,'
           '"forced_expire":false,"sender":"a@example.com","recipients":[{"address":"b@example.com",'
           '"delay_reason":"connect to example.com: timed out"}]}\n')
    q = agent.parse_queue(out)
    assert q == [{"id": "4ABC123DEF", "sender": "a@example.com", "recipients": ["b@example.com"], "size": 2048,
                  "arrival": 1700000000, "queue": "deferred", "reason": "connect to example.com: timed out"}]


def test_parse_quota():
    out = ("Username\tType\tName\tValue\tLimit\t%\n"
           "u@example.com\tSTORAGE\tUser quota\t2048\t1048576\t0\n"
           "u@example.com\tMESSAGE\tUser quota\t17\t-\t0\n")
    assert agent.parse_quota(out) == [{"address": "u@example.com", "bytes": 2048 * 1024, "messages": 17}]


def test_queue_id_re():
    assert agent.QUEUE_ID_RE.match("4ABC123DEF")
    assert not agent.QUEUE_ID_RE.match("abc; rm -rf /")
