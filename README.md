# Instrumentor

Instrumentation library for python apps. Backed by Redis and exposes to Prometheus

-- Work in progress --  
-- Docs as design document --

# About Instrumentor

When building our multi utility AMR solution Utilitarian we wanted to add effective 
metrics handling to expose our metrics to be scraped by Prometheus.

We could not find an existing solution that would do this in a desirable way. There is 
for example [django-prometheus](https://github.com/korfuri/django-prometheus), but 
essentially they require you to switch out most the django stack to their own classes 
so that that has monitoring built in. It also uses the official 
[python prometheus client](https://github.com/prometheus/client_python) which seems to 
do a good job, but it seems hard to use in web-apps that are multiprocess or 
deployed across several servers. It also requires each process to start its own 
http server that Prometheus can scrape. So if you have an application that scales 
automatically it would be troublesome to to keep track of the instances that should be 
scraped since each instance only keeps data about its on process. 

We also have several little services processing messages coming in from different 
queues and we would like to instrument those too without starting up separate 
webservers for each little job.

We also want to instrument our celery jobs, but since we don't have control over 
exactly where they are executed we thing a centralised approach is valid.

So we want to design Instrumentor to be a metrics utility that can be used in several 
different of types of applications that uses a  shared store for the metrics so 
that we can keep all our metrics in once place and give us control on how we expose them.

# Design

Since Prometheus data pretty much is a collection of counters over time we can model 
all our metrics by using counters that Prometheus scrapes at desired intervals. 
The best way of keeping track of counters in a distributed environment is [Redis](https://redis.io/).  

So all metrics are sent to Redis and we can choose to expose a web applications metrics 
in each web application by transforming the data in redis to and appropriate Prometheus format.
We could also create a separate web application which only functions as a metrics 
endpoint for instrumented applications.

Since we also have a predetermined format in Redis other application in other 
programming languages could make use of the same structure and we have a common way to 
handle application logging across all our services.

## Namespacing

Each applications metrics should live in a separate namespace. This makes it possible 
have several applications metrics stored in the same Redis instance. It also makes it 
easy to move applications metrics to other Redis instances if you require separation.

To create a namespace we use redis hashes.

## Metrics

General for all metric types is that we have a collection of counters, a name and a 
description.

By defining a specific format for the key names in the hash we can encode the data we 
as needed.

We also need to keep information about different labels on each metric. Each 
combination of different lables should create a separate counter. Labels should be 
sorted so that each distinct combination of labels only generate one counter. Example
metric with labels {green, red, yellow} should increase the same counter as metric 
with label {yellow, red, green} to keep down the number of counters and reduce parsing 
need. 

To simplify parsing and to be able to read raw data a bit easier we should also include 
hint about the metric type in the key.

Rules for Prometheus metrics should also apply. For example Histogram and Summary is 
just several counters with predefined label names. These label names should also be 
protected from misuse on other types. 

The library will assume that normal Prometheus best practices are used when defining 
metrics and will not enforce any rules or checks on the user. For example, don't use 
too many labels. Each label creates a time series in Prometheus and also a counters 
in Redis.

Each metrics should have a key that ends with _description to hold the description of 
the metrics. There is need for some form of control to not keep sending the description 
on every update.

### Encoding format

To name the different values we should use a combination of values separated with the 
recommended separation character of semicolon.

{metric_name}:{extension}:{labels}

labels should be encoded with label name and label text in a comma separated list

{label_name}="{label_value}",{label_name}="{label_value}"

Example metric api_http_requests:

```
api_http_requests_total::method="POST",handler="/messages"
```


### Counter

A counter is a cumulative metric that represents a single increasing counter whose 
value can only increase or be reset to zero on restart. 

Example for http_requests
```
api_http_requests_total::                                         -> 32   # counter without labels
api_http_requests_total::method="POST",handler="/messages"        -> 12  # counter matching the labels
api_http_requests_total:description::                             ->  "Total HTTP Requets to API"
api_http_requests_total:type::                                    -> "counter"
```

### Gauge

A Prometheus Gauge is a value that can increase and decrease.

Example for temperature
```
temperature_celcius::                                     -> 32   # counter without labels
temperature_celcius::location="MainOffice",sensor="34"    -> 12  # counter matching the labels
temperature_celcius:descri ption:                         -> "Total HTTP Requets to API"
temperature_celcius:type:                                 -> "gauge"
```

### Histogram

A histogram samples observations (usually things like request durations or response 
sizes) and counts them in configurable buckets. It also provides a sum of all 
observed values. Prometheus histograms are cumulative histograms so all obervations 
that fits in other buckets are added.

You will need to predefine your buckets sizes.

Example other data format
```
http_request_duration_seconds:bucket:le="0.05"    ->  24054
http_request_duration_seconds:bucket:le="0.1"     ->  33444
http_request_duration_seconds:bucket:le="0.2"     ->  100392
http_request_duration_seconds:bucket:le="0.5"     ->  129389
http_request_duration_seconds:bucket:le="1"       ->  133988
http_request_duration_seconds:bucket:le="+Inf"    ->  144320
http_request_duration_seconds:sum:                 ->  53423
http_request_duration_seconds:count:               ->  144320 
http_request_duration_seconds:description:         ->  "Duration of HTTP requests"
http_request_duration_seconds:type:                ->  "histogram"
```
To save some bytes extensions are encoded with the letter they start with. 
description=d, sum=s, count=c, type=t, bucket=b. The type value is also 
shortened: counter=c, gauge=g, histogram=h, summary=s

### Summary

Is similar to histogram but instead of using buckets you specify percentiles. 

You will need to provide a max value to calculate the percentile against.

Values above the max value should be set to 1 ??

Add counter that will increase for each value that is over max value.

```
rpc_duration_seconds::quantile:="0.01"      -> 3102
rpc_duration_seconds::quantile="0.05"       -> 3272
rpc_duration_seconds::quantile="0.5"        -> 4773
rpc_duration_seconds::quantile="0.9"        -> 9001
rpc_duration_seconds::quantile="0.99"       -> 76656
rpc_duration_seconds:sum:                   -> 1.7560473e+07
rpc_duration_seconds:count:                 -> 2693
rpc_duration_seconds:description:           -> "Duration of RPC" 
rpc_duration_seconds:type:                  ->  "summary"
```


## Interaction with Redis

By setting the eager flag to true, all metrics updates will be sent directly instead of
at a single point in time when `.store()`is called. To make the communication with 
redis efficient pipelining is used. 

## High level API

We try to follow the directions from Prometheus when 
[developing client libraries.](https://prometheus.io/docs/instrumenting/writing_clientlibs/)

### CollectorRegistry

Main class for managing the metrics in your application. You will register each metric 
in the `CollectorRegistry` and it will handle all communication to Redis.

```

reg = CollectorRegistry(redis_host='localhost', 
                        redis_port='6372', 
                        redis_db=0,
                        namespace='myapp' 
                        eager=False)
                        

http_requests_total = Counter(.....)

reg.register(http_requests_total)
reg.unregister(http_requests_total)  # incase it is needed...

```


### Metrics


```

http_requests_total = Counter(name='http_requests_total', 
                              description='Total amount of http requests', 
                              allowed_labels={'code', 'method', 'path'})
                              
                              
http_requests_total.inc()   # increment counter by 1
http_request_total.inc(3)   # increment counter by 3

http_requests_total.inc(labels={"code": "200"})

````


```
temperature_celcius = Gauge(name='temperature_celcius',
                            description='Temperature in celcius',
                            allowed_labels={'location', 'sensor'},
                            start_value=2)
                            
temperature_celcius.inc()
temperature_celcius.inc(3)
temperature_celcius.dec()
temperature_celcius.dec(3)
termperature_celcius.set(5)
```

```

response_time_seconds = Histogram(name='response_time_seconds', 
                                  description='Response time in seconds',
                                  allowed_labels={'path', 'method'},
                                  buckets={0.05, 0.2, 0.3, 0.7, 0.9, 2})
                                  

response_time_seconds = LinearHistogram(name='response_time_seconds', 
                                        description='Response time in seconds',
                                        allowed_labels={'path', 'method'},
                                        start=0.5, width=20, count=10)
      
response_time_seconds = ExponentialHistogram(name='response_time_seconds', 
                                             description='Response time in seconds',
                                             allowed_labels={'path', 'method'},
                                             start=0.5, factor=2, count=10)                            
                                  

response_time_seconds.observe(34)


```


```

response_time_seconds = Summary(name='response_time_seconds', 
                                  description='Response time in seconds',
                                  allowed_labels={'path', 'method'},
                                  quantile={0.05, 0.2, 0.3, 0.7, 0.9})
     


response_time_seconds.observe(34)

```


### Instrumenting


```python
# In a collection module, ex mymetrics.py
import redis
import instrumentor

r = redis.Redis()
reg = instrumentor.CollectionRegistry(redis_client=r, namespace='myapp')

http_requests_total = instrumentor.Counter(name='http_request_total', description='Total amount of http requests')

reg.register(http_requests_total)

#In other module:

from mymetrics import http_requests_total

http_requests_total.inc()

```

Main use cases are counting or timing.

We provide a simple decorator that can be used for counting method calls.

It is available for counters and gauges.

```python
from mymetrics import http_request_total

@http_request_total.count
def my_func():
    pass
     
```

It is also possible to use the general decorator and supply the metric as an input arg.

```python

from instrumentor import count
from  mymetrics import http_requests_total

@count(metric=http_requests_total, labels={"code": "200"})
def my_func():
    pass


```

Timing is done via decorator on the metric instance or the general decorator/context manager.

```python
import instrumentor
from mymetrics import my_func_runtime_seconds
import time
@my_func_runtime_seconds.time
def myfund():
    time.sleep(1)
    

# or

@instrumentor.timer(metric=my_func_runtime_seconds)
def myfunc():
    pass
    
    
with instrumentor.timer(
    metric=my_func_runtime_seconds, 
    milliseconds=True,
    labels={"my-label": "test"}):
    
    time.sleep(1)
        
        


```

Other special instrumenting cases can be built using the normal functions on metrics.


#### Instrumenting Django

Collecting metrics about requests and response times are probably better to do in the 
load balancer/reverse proxy.

We mainly want to instrument aspects of out application.

Registry should be in its own module and be imported in `__init__` so it gets loaded by 
default (simmilar to setup of Celery)

By making a middleware class that calls `transfer()` on the register
when the response is returning we can make use of pipelining and 
update all metrics that where affected during the request.

#### Instrumenting Flask

Similar to django. 

Registry probably be made as an extension so it can be saved in the global app context.

have the `transfer()` be registed to be run using Flasks `after_request` decorator.


#### Instrumenting Celery Tasks

By making a new decorator that can wrap the normal task decorator it is possible 
to add instrumenting capabilities when running a task.
after task has run call `transfer()` on the registry.
It should also be possible to add celery specific metrics as task execution time, 
memory consumption etc. 



## Exposition

Since the format in redis is predefined an exposition client could be written in 
any language. Included in the library is a very simple exposition client.
The results from the client can then be returned in a for example a django view.
The client only knows about the namespace it should collect and does so with the 
HGETALL command in Redis.

Metrics could be exposed in the web application that you are instrumenting or 
a separate webapp just for exposition could be set up, that also could expose 
several namespaces (applications). This way scraping is decoupled from you application 
and can be scaled accordingly.





 
 
 


  


