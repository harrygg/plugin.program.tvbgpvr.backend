# -*- coding: utf-8 -*-
import os
import re
from urllib import unquote
from utils import *
from bottle import route, default_app, HTTPResponse

__DEBUG__ = False
app       = default_app()
port      = settings.port
language  = this.getLocalizedString


@route('/tvbgpvr.backend/playlist', method=GET)
def get_playlist():
  """
    Displays the m3u playlist
    :return: m3u
  """
  log("get_playlist() started")
  body = None
  body = M3U_START_MARKER + NEWLINE
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
  return HTTPResponse("", 
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

  ### If this is the first requst by the player
  ### return a dummy response to prevent duplicate requests 
  ### causing failures on some middleware servers 
  if VERSION > 16 and not os.path.isfile(session):
    with open(session, "w") as s: 
      s.write("")
    log("Session created!")

    log("get_stream() ended")
    return HTTPResponse(M3U_START_MARKER, 
                      status=200, 
                      **headers)
  
  clear_session()

  ### If this is the second request by the player
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
        if line.startswith(M3U_INFO_MARKER) and name in line:
          found = True
    
    if not found:
      log("Stream not found for channel %s" % name)
      return HTTPResponse(body, status=404)

    if __DEBUG__:
      body = location
      return HTTPResponse(body, 
                      status=200)
                      
    headers['Location'] = location

  except Exception as er:
    body = str(er)
    log(str(er), 4)
    
  log("get_stream() ended")
  
  return HTTPResponse(body, 
                      status=302, 
                      **headers)