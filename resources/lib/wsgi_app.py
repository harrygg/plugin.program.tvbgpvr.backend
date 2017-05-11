# -*- coding: utf-8 -*-
import os
import re
import requests
from utils import *
from urllib import unquote
from bottle import route, default_app, HTTPResponse

__DEBUG__ = True
app       = default_app()
port      = settings.port

@route('/tvbgpvr.backend/playlist', method=GET)
def get_playlist():
  """
    Displays the m3u playlist
    :return: m3u
  """
  log("get_playlist() started")
  body = "#EXTM3U\n"
  try:
    with open(pl_path) as file:
      body = file.read() 
  except Exception as er:
    body = str(er)
    log(str(er))

  headers = {}
  if not __DEBUG__:
    headers['Content-Type'] = "audio/mpegurl"
    
  log("get_playlist() ended")
  
  return HTTPResponse(body, 
                      status=200, 
                      **headers)


@route('/tvbgpvr.backend/stream/<name>', method=HEAD)
def get_stream(name):
  return HTTPResponse(None, 
                      status=200)


@route('/tvbgpvr.backend/stream/<name>', method=GET)
def get_stream(name):
  '''
    Get the m3u stream url
    Returns 302 redirect
  '''
  headers  = {}
  body     = None
  location = None

  log("get_stream() started")
  ### Kodi 17 sends 2 GET requests for a resource which may cause 
  ### stream invalidation on some middleware servers. If this is 
  ### the first request return a dummy response and handle the 2nd
  if VERSION > 16 and not os.path.isfile(session):
    open(session, "w").close()
    log("get_stream() ended. Session created!")
    return HTTPResponse(body, 
                      status = 200, 
                      **headers)
  
  clear_session()

  ### If this is the 2nd request by the player
  ### redirect it to the original stream  
  try:  
    name = unquote(name)
    found = False
    
    with open(pl_cache) as file:
      for line in file:
        if found and line.rstrip():
          location = line
          matches = re.compile("(\|.*)").findall(location)
          if len(matches):
            location = location.replace(matches[0], "")
          log("%s stream found: %s" % (name, location))
          break
        if line.startswith("#EXTINF") and name in line:
          found = True
    
    if not found:
      notify_error(translate(32008) % name)
      return HTTPResponse(body, 
                          status = 404)

    if __DEBUG__:
      return HTTPResponse(location,
                          status = 200)
                      
    headers['Location'] = location

  except Exception as er:
    body = str(er)
    log(str(er), 4)
    
  log("get_stream() ended")
  return HTTPResponse(body, 
                      status = 302, 
                      **headers)