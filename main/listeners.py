import socket
from pykka import ThreadingActor
from abc import abstractmethod
from main.utils import recv_tcp_message, send_tcp_message
from main.messages import DNSMessage
import logging


class BaseListener(ThreadingActor):
    def __init__(self, host, port, resolver_ref):
        super().__init__()
        self._host = host
        self._port = port
        self._resolver_ref = resolver_ref
        self._socket = None

    def on_receive(self, message):
        logging.debug('[{}] received message: {}'.format(self.__class__.__name__, message))
        if message.get('command') == 'start':
            self.open()
            self.loop_produce()

        elif message.get('command') == 'stop':
            self.close()

        elif message.get('command') == 'produce':
            self.loop_produce()

    def loop_produce(self):
        try:
            self.produce()
        except socket.timeout:
            logging.debug('[{}] time out'.format(self.__class__.__name__))
        except Exception as e:
            logging.error('[{}] unhandled exception: {}'.format(self.__class__.__name__, e))
        finally:
            self.actor_ref.tell({'command': 'produce'})

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def produce(self):
        pass

    def close(self):
        if self._socket is not None:
            logging.info('[{}] closing socket'.format(self.__class__.__name__))
            self._socket.close()
            self._socket = None

    def on_stop(self):
        self.close()


class UDPListener(BaseListener):
    def open(self):
        logging.info('[{}] opening socket'.format(self.__class__.__name__))
        self._socket = socket.socket(socket.AF_INET,     # Internet
                                     socket.SOCK_DGRAM)  # UDP
        self._socket.settimeout(5)
        self._socket.bind((self._host, self._port))

    def produce(self):
        data, addr = self._socket.recvfrom(2 ** 16)
        logging.debug('[{}] received data from `{}`: {}'.format(self.__class__.__name__, addr, data))

        response = self._resolver_ref.ask({'command': 'resolve', 'data': data})
        logging.debug('[{}] response is: {}'.format(self.__class__.__name__, response))

        if len(response) > 512:
            logging.info('UDP response is `{}` bytes length, truncating'.format(len(response)))
            response = DNSMessage.parse(response)[0]
            response.with_TC(is_truncated=True)
            response = response.to_bytes()[:512]

        self._socket.sendto(response, addr)


class TCPListener(BaseListener):
    def open(self):
        logging.info('[{}] opening socket'.format(self.__class__.__name__))
        self._socket = socket.socket(socket.AF_INET,      # Internet
                                     socket.SOCK_STREAM)  # TCP
        self._socket.settimeout(5)
        self._socket.bind((self._host, self._port))
        self._socket.listen()

    def produce(self):
        conn, addr = self._socket.accept()
        with conn:
            logging.debug('[{}] connected by {}'.format(self.__class__.__name__, addr))
            data = recv_tcp_message(conn)
            logging.debug('[{}] received data: {}'.format(self.__class__.__name__, data))

            response = self._resolver_ref.ask({'command': 'resolve', 'data': data})
            logging.debug('[{}] response is: {}'.format(self.__class__.__name__, response))
            send_tcp_message(conn, response)
        logging.debug('[{}] {} disconnected'.format(self.__class__.__name__, addr))
