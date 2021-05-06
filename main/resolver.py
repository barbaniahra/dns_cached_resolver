import pykka
from main.messages import DNSMessage, DNSRecord, DNSQuestion
from main.utils import recv_tcp_message, send_tcp_message
import socket
import logging
import random
from main.constants import *
import sqlite3


class Resolver(pykka.ThreadingActor):
    def __init__(self, root_servers):
        super(Resolver, self).__init__()
        self._root_servers = root_servers
        self.cache = None

    def _init_cache(self):
        if not self.cache:
            self.cache = sqlite3.connect('cache.db')

        try:
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
            cur.execute("""
            SELECT changes();
            """)
            logging.info("Cleared up `{}` entries from cache".format(list(cur))[0][0])
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

    def _lookup_answer(self, question: DNSQuestion):
        try:
            cur = self.cache.cursor()
            cache = list(cur.execute("""
            SELECT data
            FROM cache
            WHERE LOWER(name) = LOWER(?) and type = ?
            ORDER BY RANDOM()
            LIMIT 1;
            """, (question.qname, question.qtype)))

            if cache:
                record = DNSRecord.parse(cache[0][0], 0)[0]
                logging.info('Got record `{}` from cache'.format(record))
                return record

        except Exception as e:
            logging.warning("Error with lookup answer: `{}`, will continue w/o it".format(e))

    def _lookup_delegate(self, qname):
        try:
            cur = self.cache.cursor()
            delegate = list(cur.execute("""
            SELECT a_data.data
            FROM cache ns_data
            JOIN cache a_data ON LOWER(ns_data.ns) = LOWER(a_data.name)
            WHERE LOWER(ns_data.name) = LOWER(?) 
				and ns_data.type = 2
				and a_data.type in (1, 28)
            ORDER BY RANDOM()
            LIMIT 1;
            """, (qname,)))

            if delegate:
                delegate = DNSRecord.parse(delegate[0][0], 0)[0]
                delegate = delegate.rname, delegate.as_ip()
                logging.info('Got delegate `{}` from cache'.format(delegate))
                return delegate

        except Exception as e:
            logging.warning("Error with lookup delegate: `{}`, will continue w/o it".format(e))

    def on_receive(self, message):
        self._init_cache()
        self._cleanup_cache()

        if message.get('command') == 'resolve':
            data = message['data']
            return self.resolve(data)

    def resolve(self, data, recursion_level=0):
        server = None
        request, i = DNSMessage.parse(data)

        if recursion_level == 10:
            response = request.with_AA(is_authoritative=False).with_RA(is_available=True).as_response()
            logging.info('Giving up {}'.format(response))
            return response.to_bytes()

        answers = []
        for question in request.questions:
            answer = self._lookup_answer(question)
            if answer:
                answers.append(answer)
            elif question.qtype in {A, AAAA}:
                # find a suffix NS record:

                suffixes = []
                suffix = ''
                for s in reversed(question.qname.split('.')):
                    suffix = s + suffix
                    suffix = '.' + suffix

                    if suffix.lstrip('.'):
                        suffixes.append(suffix.lstrip('.'))

                for suffix in reversed(suffixes):
                    answer = self._lookup_delegate(suffix)
                    if answer:
                        server = answer
                        break

        if len(answers) >= request.header.qdcount:
            request.answers = answers
            request.header.ancount = len(answers)
            answer = request.with_AA(is_authoritative=False).with_RA(is_available=True).as_response()
            logging.info('Got all answers from cache, returning: {}'.format(answer))
            return answer.to_bytes()

        if server is None:
            # begin by asking random root server
            server = ('.', random.choice(self._root_servers))

        with socket.socket(socket.AF_INET,
                           socket.SOCK_STREAM) as s:
            s.connect((server[-1], 53))
            response = self.probe(s, request, server)

            to_check = []
            for authority in response.authorities:
                if authority.rtype != NS:
                    continue
                if not list([
                    a for a in request.additionals
                    if a.rname.lower() == authority.rdata.decode().lower()
                        and a.rtype in {A, AAAA}
                ]):
                    for type in [A, AAAA]:
                        to_check.append(DNSQuestion(authority.rdata.decode(), type, qclass=1))
            for q in to_check:
                new_query = request.with_RD(is_desired=False)
                new_query.questions = [q]
                new_query.header.qdcount = 1
                self.probe(s, new_query, server)

            return self.resolve(data, recursion_level + 1)

    def probe(self, s, request, server):
        # non recursive
        request = request.with_RD(is_desired=False)
        send_tcp_message(s, request.to_bytes())

        logging.info('Request to {}: {}'.format(server, request))

        resp_data = recv_tcp_message(s)
        response = DNSMessage.parse(resp_data)[0]

        for r in response.records():
            self._insert_cache(r)

        logging.info('Response from {}: {}'.format(server, response))
        return response
