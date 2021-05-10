import dataclasses
from typing import List, Optional
from main.utils import *
from copy import deepcopy
from main.constants import *
import ipaddr


@dataclasses.dataclass
class DNSHeader:
    id: int
    flags: str
    qdcount: int
    ancount: int
    nscount: int
    arcount: int

    @staticmethod
    def parse(data, i):
        id, flags, questions_count, answers_count, authority_count, additional_count = struct.unpack('!HHHHHH', data[i: i+12])
        i += 12

        return DNSHeader(id, "{0:0>16b}".format(flags), questions_count, answers_count, authority_count, additional_count), i

    def to_bytes(self) -> bytes:
        return struct.pack('!HHHHHH', self.id, int(self.flags, base=2), self.qdcount, self.ancount, self.nscount, self.arcount)

    def rcode(self):
        return int(self.flags[12:], base=2)

@dataclasses.dataclass
class DNSQuestion:
    qname: str
    qtype: int
    qclass: int

    @staticmethod
    def parse(data, i):
        qname, i = parse_name(data, i)
        qtype, qclass = struct.unpack('!HH', data[i:i + 4])
        i += 4

        return DNSQuestion(qname, qtype, qclass), i

    def to_bytes(self) -> bytes:
        return encode_name(self.qname) + struct.pack('!HH', self.qtype, self.qclass)


@dataclasses.dataclass
class DNSRecord:
    rname: str
    rtype: int
    rclass: int
    ttl: int
    rdlength: int
    rdata: bytes

    @staticmethod
    def parse(data, i):
        rname, i = parse_name(data, i)
        rtype, rclass, ttl, rdlength = struct.unpack('!HHIH', data[i:i + 10])
        i += 10

        if rtype == NS:
            name, _ = parse_name(data, i)
            rdata = name.encode()
            i += rdlength
            rdlength = len(rdata)
        else:
            rdata = data[i:i+rdlength]
            i += rdlength

        return DNSRecord(rname, rtype, rclass, ttl, rdlength, rdata), i

    def to_bytes(self) -> bytes:
        return encode_name(self.rname) + struct.pack('!HHIH', self.rtype, self.rclass, self.ttl,  self.rdlength) + self.rdata

    def as_ip(self) -> Optional[str]:
        b = ipaddr.Bytes(self.rdata)
        if self.rdlength == 16:
            return str(ipaddr.IPv6Address(b))
        if self.rdlength == 4:
            return str(ipaddr.IPv4Address(b))


@dataclasses.dataclass
class DNSMessage:
    header: DNSHeader
    questions: List[DNSQuestion]
    answers: List[DNSRecord]
    authorities: List[DNSRecord]
    additionals: List[DNSRecord]

    @staticmethod
    def from_question(question):
        return DNSMessage(
            DNSHeader(id=123,
                      flags='0' * 16,
                      qdcount=1,
                      ancount=0,
                      nscount=0,
                      arcount=0),
            questions=[question],
            answers=[],
            authorities=[],
            additionals=[]
        )


    @staticmethod
    def parse(data, i=0):
        header, i = DNSHeader.parse(data, i)
        questions = []
        for _ in range(header.qdcount):
            question, i = DNSQuestion.parse(data, i)
            questions.append(question)

        answers, authorities, additionals = [], [], []
        for arr, count in [[answers, header.ancount],
                           [authorities, header.nscount],
                           [additionals, header.arcount]]:
            for _ in range(count):
                resource, i = DNSRecord.parse(data, i)
                arr.append(resource)

        return DNSMessage(header, questions, answers, authorities, additionals), i

    def to_bytes(self) -> bytes:
        return self.header.to_bytes() + b''.join(map(lambda x: x.to_bytes(), (self.questions + self.answers +
                                                                              self.authorities + self.additionals)))

    def _with_flag(self, flag_index, flag_value: bool):
        copy = deepcopy(self)
        flags = list(copy.header.flags)
        flags[flag_index] = str(int(flag_value))
        flags = ''.join(flags)
        copy.header.flags = flags
        return copy

    def as_response(self):
        return self._with_flag(0, True)

    def with_AA(self, is_authoritative: bool):
        return self._with_flag(5, is_authoritative)

    def with_TC(self, is_truncated: bool):
        return self._with_flag(6, is_truncated)

    def with_RD(self, is_desired: bool):
        return self._with_flag(7, is_desired)

    def with_RA(self, is_available: bool):
        return self._with_flag(8, is_available)

    def with_rcode(self, rcode: int):
        bits = "{0:0>4b}".format(rcode)

        result = self
        for i, v in enumerate(bits):
            result = result._with_flag(12 + i, v == '1')

        return result

    def records(self):
        yield from self.answers
        yield from self.authorities
        yield from self.additionals
