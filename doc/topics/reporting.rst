=========
Reporting
=========

Curtin is capable of reporting its progress via the reporting framework.
This enables the user to obtain status information from curtin.

Events
------
Reporting consists of notifcation of a series of 'events.  Each event has:
 - **event_type**: 'start' or 'finish'
 - **description**: human readable text
 - **name**: and id for this event
 - **result**: only present when event_type is 'finish', its value is one of "SUCCESS", "WARN", or "FAIL".  A result of WARN indicates something is likely wrong, but a non-fatal error.  A result of "FAIL" is fatal.
 - **origin**: literal value 'curtin'
 - **timestamp**: the unix timestamp at which this event occurred

names are unique and hierarchical. For example, a series of names might look like:
 - cmd-install (start)
 - cmd-install/stage-early (start)
 - cmd-install/stage-early (finish)
 - cmd-install (finish)

You are guaranteed to always get a finish for each sub-item before finish of
the parent item, and guaranteed to get finish for all events.
A FAIL result of a sub-item will bubble up to its parent item.


Configuration
-------------
Reporting configuration is done through the ``reporting`` item in config.  An
example config::

   reporting:
     keyname1:
       type: webhook
       endpoint: "http://127.0.1.1:8000/"
     keyname2:
       type: print

   install:
     log_file: /tmp/install.log
     post_files: [/tmp/install.log, /var/log/syslog]

Each entry in the ``reporting`` dictionary must be a dictionary.  The key is
only used for reference and to aid in config merging.

Each entry must have a 'type'.  The currently supported values are:
 - **log**: logs via python logger
 - **print**: prints messages to stdout (for debugging)
 - **webhook**: posts json formated data to a remote url.  Supports Oauth.


Additionally, the webhook reporter will post files on finish of curtin.  The user can declare which files should be posted in the ``install`` item via ``post_files`` as shown above.  If post_files is not present, it will default to the value of log_file.


Webhook Reporter
----------------
The webhook reporter posts the event in json format to an endpoint.  To enable,
provide curtin with config like::

  reporting:
    mylistener:
      type: webhook
      endpoint: http://example.com/endpoint/path
      consumer_key: "ck_foo"
      consumer_secret: "cs_foo"
      token_key: "tk_foo"
      token_secret: "tk_secret"

The ``endpoint`` key is required. Oauth information (consumer_key,
consumer_secret, token_key, token_secret) is not required, but if provided
then oauth will be used to authenticate to the endpoint on each post.

Example Events
~~~~~~~~~~~~~~
The following is an example event that would be posted::

  {
   "origin": "curtin",
   "timestamp": 1440688425.6038516,
   "event_type": "start",
   "name": "cmd-install",
   "description": "curtin command install"
  }


The post files will look like this::

  {
   "origin": "curtin",
   "files": [
      {
        "content: "fCBzZmRpc2s....gLS1uby1yZX",
        "path": "/var/log/curtin/install.log",
        "encoding": "base64"
      },
      {
        "content: "fCBzZmRpc2s....gLS1uby1yZX",
        "path": "/var/log/syslog",
        "encoding": "base64"
      }
   ],
   "description": "curtin command install",
   "timestamp": 1440688425.6038516,
   "name": "cmd-install",
   "result": "SUCCESS",
   "event_type": "finish"
  }


Example Http Request
~~~~~~~~~~~~~~~~~~~~
The following is an example http request from curtin::

  Accept-Encoding: identity
  Host: localhost:8000
  Content-Type: application/json
  Connection: close
  User-Agent: Curtin/0.1
  Content-Length: 156

  {
   "origin": "curtin",
   "timestamp": 1440688425.6038516,
   "event_type": "start",
   "name": "cmd-install/stage-early",
   "description": "preparing for installation"
  }


Development / Debug Reporting
-----------------------------
For debugging and development a simple web server is provided in
`tools/report-webhook-logger`.  

Run the web service like::

   ./tools/report-webhook-logger 8000

And then run your install with appropriate config, like::
 
  sudo ./bin/curtin -vvv install \
     --set install/logfile=/tmp/foo \
     --set reporting/mypost/type=webhook \
     --set reporting/mypost/endpoint=http://localhost:8000/
     file://$root_tgz


Legacy Reporter
---------------
The legacy 'reporter' config entry is still supported.  This was utilized by
MAAS for start/end and posting of the install log at the end of isntallation.

Its configuration looks like this:

**Legacy Reporter Config Example**::

 reporter:
   url: http://example.com/your/path/to/post
   consumer_key: "ck_foo"
   consumer_secret: "cs_foo"
   token_key: "tk_foo"
   token_secret: "tk_secret"

