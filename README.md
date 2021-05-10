# DNS caching server
The following TYPEs are supported:
- A
- AAAA
- NS
- PTR

# Installation
```
pip3 install .
 ```

# Running

Start with `dns_cached_resolver`. If you want to specify parameters (e.g. location of cache file or custom root servers), see #Parameters section

# Examples
1) `A` records:
```
% dig @localhost opendata.edu.gov.ru A
...
;; ANSWER SECTION:
opendata.edu.gov.ru.	300	IN	A	85.142.23.118
...
```

2) `AAAA` records:
```
% dig @localhost mail.google.com AAAA
...
;; ANSWER SECTION:
mail.google.com.	604800	IN	CNAME	googlemail.l.google.com.
googlemail.l.google.com. 300	IN	AAAA	2a00:1450:4010:c1c::11
googlemail.l.google.com. 300	IN	AAAA	2a00:1450:4010:c1c::53
googlemail.l.google.com. 300	IN	AAAA	2a00:1450:4010:c1c::13
googlemail.l.google.com. 300	IN	AAAA	2a00:1450:4010:c1c::12
...
```

3) `NS`:
```
% dig +tcp @localhost mail.yandex.ru NS
...
;; ANSWER SECTION:
mail.yandex.ru.		3600	IN	NS	ns3.yandex.ru.
mail.yandex.ru.		3600	IN	NS	ns4.yandex.ru.
mail.yandex.ru.		3600	IN	NS	ns6.yandex.ru.
...
```
4) Reverse DNS (`PTR`):
```
% dig @localhost 4.4.8.8.in-addr.arpa PTR
...
;; ANSWER SECTION:
4.4.8.8.in-addr.arpa.	86400	IN	PTR	dns.google.
...
```

# Parameters
```
 % dns_cached_resolver --help
usage: dns_cached_resolver [-h] [-c CONFIG] --logging_level LOGGING_LEVEL --protocol {tcp,udp,both} --host HOST --port PORT --root_servers ROOT_SERVERS --cache_location CACHE_LOCATION

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Config file path
  --logging_level LOGGING_LEVEL
                        Logging level
  --protocol {tcp,udp,both}
  --host HOST
  --port PORT
  --root_servers ROOT_SERVERS
  --cache_location CACHE_LOCATION

Args that start with '--' (eg. --logging_level) can also be set in a config file (/usr/local/anaconda3/envs/dns_cached_resolver/dns_cached_resolver_resources/config.ini or specified via -c). Config file
syntax allows: key=value, flag=true, stuff=[a,b,c] (for details, see syntax at https://goo.gl/R74nmi). If an arg is specified in more than one place, then commandline values override config file values
which override defaults.
```

See `resources/config.ini` for default configs.