import pykka
from main.messages import DNSMessage, DNSRecord, DNSQuestion
from main.utils import recv_tcp_message, send_tcp_message
import socket
import logging
from main.constants import *
from typing import List, Union
import sqlite3
import random


class Resolver(pykka.ThreadingActor):
    MAX_RECURSION = 10

    def __init__(self, root_servers, cache_location):
        super(Resolver, self).__init__()
        self._root_servers = [
            ('.', ns)
            for ns in root_servers
        ]
        self.cache_location = cache_location
        self.cache = None

    def _init_cache(self):
        try:
            if not self.cache:
                self.cache = sqlite3.connect(self.cache_location)

            self.cache.cursor().execute("""
            CREATE TABLE IF NOT EXISTS cache (name TEXT, type INT, ttl INT, insertion_time INT, data BLOB, ns TEXT);
            """)
            self.cache.commit()
        except Exception as e:
            logging.warning("Error with cache init: `{}`, will continue w/o it".format(e))

    def _cleanup_cache(self):
        try:
            cur = self.cache.cursor()
            cur.execute("""
            DELETE FROM cache
            WHERE strftime('%s', 'now') - insertion_time > ttl;
            """)
            self.cache.commit()
            changes = list(cur.execute("""
            SELECT changes();
            """))[0][0]
            logging.info("Cleared up `{}` entries from cache".format(changes))
        except Exception as e:
            logging.warning("Error with cache cleanup: `{}`, will continue w/o it".format(e))

    def _insert_cache(self, record: DNSRecord):
        try:
            cur = self.cache.cursor()
            ns = None if record.rtype != NS else record.rdata.decode()
            cur.execute("""
            DELETE FROM cache
            WHERE name = ? and type = ? and ns = ?;
            """, (record.rname, record.rtype, ns))

            cur.execute("""
            INSERT INTO cache(name, type, ttl, insertion_time, data, ns)
            VALUES (?, ?, ?,  strftime('%s', 'now'), ?, ?);
            """, (record.rname, record.rtype, record.ttl, record.to_bytes(), ns))

            self.cache.commit()
            logging.info("Saved record `{}` into cache".format(record))
        except Exception as e:
            logging.warning("Error with cache insert: `{}`, will continue w/o it".format(e))

    def _lookup_answer(self, question: DNSQuestion) -> List[DNSRecord]:
        try:
            cur = self.cache.cursor()
            results = list(cur.execute("""
            SELECT DISTINCT data
            FROM cache
            WHERE LOWER(name) = LOWER(?) and type = ?
            ORDER BY RANDOM();
            """, (question.qname, question.qtype)))

            if results:
                records = [
                    DNSRecord.parse(row[0], 0)[0]
                    for row in results
                ]
                logging.info('Got records `{}` from cache'.format(records))
                return records

        except Exception as e:
            logging.warning("Error with lookup answer: `{}`, will continue w/o it".format(e))

    def _lookup_delegates(self, qname):
        try:
            cur = self.cache.cursor()
            results = list(cur.execute("""
            SELECT DISTINCT a_data.data
            FROM cache ns_data
            JOIN cache a_data ON LOWER(ns_data.ns) = LOWER(a_data.name)
            WHERE LOWER(ns_data.name) = LOWER(?) 
				and ns_data.type = 2
				and a_data.type == 1
            ORDER BY RANDOM();
            """, (qname,)))

            if results:
                records = [
                    (delegate.rname, delegate.as_ip())
                    for delegate in [
                        DNSRecord.parse(row[0], 0)[0]
                        for row in results
                    ]
                ]
                logging.info('Got delegates `{}` from cache'.format(records))
                return records

        except Exception as e:
            logging.warning("Error with lookup delegate: `{}`, will continue w/o it".format(e))

    def on_receive(self, message):
        self._init_cache()
        self._cleanup_cache()

        if message.get('command') == 'resolve':
            data = message['data']
            request, _ = DNSMessage.parse(data)
            if len(request.questions) != 1:
                return request.with_rcode(NOTIMPLEMENTED).as_response().to_bytes()

            if request.questions[0].qtype not in {A, AAAA, PTR, NS}:
                return request.with_rcode(NOTIMPLEMENTED).as_response().to_bytes()

            request.header.ancount = 0
            request.header.arcount = 0
            request.header.nscount = 0
            request.answers = []
            request.additionals = []
            request.authorities = []

            try:
                for _ in range(self.MAX_RECURSION):
                    result = self.answer(request.questions[0])
                    if isinstance(result, int):
                        if result == NOERROR:
                            # found new delegates, continue
                            continue
                        if result in {NAMEERROR, REFUSED, SERVERFAILURE}:
                            # error
                            logging.info('A problem occured during resolving, giving up: {}'.format(result))
                            return (request.with_AA(is_authoritative=False)
                                    .with_RA(is_available=True)
                                    .with_rcode(result)
                                    .as_response()).to_bytes()
                        else:
                            raise Exception('Unknown int result: {}'.format(result))
                    else:
                        # there might be an answer
                        request.answers = result
                        request.header.ancount = len(result)
                        logging.info('Got {} answers: {}'.format(len(result), result))
                        return (request.with_AA(is_authoritative=False)
                                       .with_RA(is_available=True)
                                       .with_rcode(NOERROR)
                                       .as_response()).to_bytes()
                return (request.with_AA(is_authoritative=False)
                               .with_RA(is_available=True)
                               .with_rcode(NOERROR)
                               .as_response()).to_bytes()
            except Exception as e:
                logging.error('Exception during resolving: [{}] {}'.format(type(e), e))
                return request.with_rcode(SERVERFAILURE).as_response().to_bytes()

    def where_to_ask(self, qname):
        suffixes = []
        suffix = ''
        for s in reversed(qname.split('.')):
            suffix = s + suffix
            suffix = '.' + suffix

            if suffix.lstrip('.'):
                suffixes.append(suffix.lstrip('.'))

        for suffix in reversed(suffixes):  # ['some.example.com.', 'example.com.', 'com.']
            delegates = self._lookup_delegates(suffix)
            if delegates:
                # find NS servers of the zone
                return delegates

        # ask root servers
        ns_servers = list(self._root_servers)
        random.shuffle(ns_servers)
        return ns_servers

    def fill_missing_ns(self, response, recursion_lvl):
        if recursion_lvl == 5:
            return

        for authority in response.authorities:
            if authority.rtype != NS:
                continue
            if not list([
                a for a in response.additionals
                if a.rname.lower() == authority.rdata.decode().lower()
                   and a.rtype in {A, AAAA}
            ]):
                # not mentioned in additionals
                logging.info('Trying to resolve NS server: {}'.format(authority.rdata.decode()))
                self.answer(DNSQuestion(authority.rdata.decode(), A, qclass=1), recursion_lvl + 1)

    def answer(self, question: DNSQuestion, recursion_lvl=0) -> Union[int, List[DNSRecord]]:
        cached = self._lookup_answer(question)
        if cached:
            return cached

        ns_servers = self.where_to_ask(question.qname)
        had_errors = False
        for ns in ns_servers:
            try:
                response = self.probe(DNSMessage.from_question(question), ns)
                if response.header.rcode() in {NAMEERROR, REFUSED}:
                    return response.header.rcode()
                if response.answers:
                    return response.answers
                if response.authorities:
                    self.fill_missing_ns(response, recursion_lvl)
                    return NOERROR
            except Exception as e:
                logging.error('Error while talking to {}: [{}] {}'.format(ns, type(e), e))
                had_errors = True
        return SERVERFAILURE if had_errors else NAMEERROR

    def probe(self, request, server):
        with socket.socket(socket.AF_INET,
                           socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((server[-1], 53))

            # non recursive
            request = request.with_RD(is_desired=False)
            send_tcp_message(s, request.to_bytes())

            logging.info('Sent request to {}: {}'.format(server, request))

            resp_data = recv_tcp_message(s)

        response = DNSMessage.parse(resp_data)[0]

        logging.info('Response from {}: {}'.format(server, response))

        for r in response.records():
            self._insert_cache(r)

        return response
