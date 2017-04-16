# -*- coding: utf-8 -*-
import os
import sys
import xbmc
import urllib
import xbmcgui
import xbmcaddon
from resources.lib.utils import *
from resources.lib.playlist import *

reload(sys)  
sys.setdefaultencoding('utf8')

__DEBUG__ = True
progress_bar = None

log("on %s " % user_agent)
if scheduled_run:
  log(translate(32004))
  
### If addon is started manually or is in debug mode, display the progress bar 
if not scheduled_run or settings.debug:
  progress_bar = xbmcgui.DialogProgressBG()
  progress_bar.create(heading=this.getAddonInfo('name'))

try:
  # Get playlist location from settings
  location = settings.url + settings.mac
  if __DEBUG__:
    location = "http://localhost/tv/playlist.dynamicnames.m3u"
  
  # Initialize the playlsit object
  pl = Playlist(location=location,
                log=log, 
                user_agent=user_agent, 
                progress=progress_bar,
                groups_from_progider=settings.groups_from_progider,
                temp_folder=profile_dir)
  
  if pl.count() == 0:
    notify_error(translate(32000))
  else:
    # Reorder playlist as per the order in the template file
    pl.reorder(template_file = get_template_file())

    ### Hide disabled channel groups
    for group in get_disabled_groups():
      pl.disable_group(group)
    
    ### Disable low quality channels
    if settings.hide_lq:
      pl.disable_quality(Quality.LQ)
    
    ### Save original playlist to disk, use it for resolving stream urls
    if not pl.save():
      notify_error(translate(32001))
      
    ### Export channel names from original playlist
    if settings.export_names:
      names_file_path = os.path.join(settings.export_to_folder, "names.txt")
      pl.save(path=names_file_path, 
              type=PlaylistType.NAMES)
    
    ### Create the playlist with static channels
    for stream in pl.streams:
      name = urllib.quote(stream.name)
      stream.url = STREAM_URL % (settings.port, name)
    
    ### Write playlist to disk
    if not pl.save(path=pl_path):
      notify_error(translate(32001))

    ### Copy playlist to additional folder if specified
    if settings.copy_playlist and os.path.isdir(settings.copy_to_folder):
      pl.save( path=os.path.join(settings.copy_to_folder, pl_name) )

except Exception, er:
  log(er, xbmc.LOGERROR)

### Schedule next run
interval = int(settings.run_on_interval) * 60
log(translate(32007) % interval)
command = "AlarmClock('ScheduledReload', %s, %s, silent)" % (RUNSCRIPT, interval)
xbmc.executebuiltin(command)

if progress_bar:
  progress_bar.close()
  
  
IMPORT = False
if IMPORT:  
  xbmc.sleep(1000)

  progress_bar = xbmcgui.DialogProgressBG()
  progress_bar.create("Importing EPG", "Importing EPG")
  percent = 0

  log("Importing EPG", 2)
  db_dir = os.path.join(profile_dir, "../../Database/").decode('utf-8')
  log("db_dir=%s" % db_dir, 2)
  db_file = os.path.join(db_dir, "Epg11.db")
  epg_file= "C:\\Users\\genevh\\Desktop\\epg.xml"

  ### Get channel idEPG's
  conn = sqlite3.connect(db_file)
  with conn:
    cursor = conn.cursor()
    sql_command = '''SELECT * FROM epg;'''
    cursor.execute(sql_command)
    log("Executing query: '%s'" % sql_command, 2)
    import resources.lib.mapping
    import xml.etree.ElementTree as ET
    from datetime import datetime
    import time
    
    ids = {}
    log("Getting ids from EPG db", 2)
    for row in cursor.fetchall():
      try: tvgid = streams_map[row[1].encode("utf-8")]["id"]
      except: tvgid = None
      
      if tvgid:
        #log("id=%s, name=%s, tvgid=%s" % (row[0], row[1], tvgid), 2)
        data = {"id": row[0], "name": row[1]}
        ids[tvgid] = data

    log("Finished getting ids from EPG db")
    #log(str(ids), 2)

    log("Clearing data in table epgtags")
    percent = 0
    progress_bar.update(percent, "Importing EPG", "Clearing data in table epgtags")
    sql_command = '''DELETE FROM epgtags;'''
    cursor.execute(sql_command)
    conn.commit()
    log("Finished clearing data in table epgtags")
  
  

    i = 0
    xbmc.sleep(3000)
    log("Starting EPG parse")
    tree = ET.parse(epg_file)
    root = tree.getroot()
    
    temp_channel = None
    for programme in root.findall("programme"):
      channel = programme.get("channel").encode("utf-8")
      if channel in ids:
        try:
        
          if channel != temp_channel:
            temp_channel = channel
            log("Adding programmes for channel %s" % channel, 2)
            percent += 2
            progress_bar.update(percent, "Importing EPG", "Parsing programmes for " + channel)
          
          i += 1
          

          bNotify = 0
          idEpg = ids[channel]["id"]
          try: sTitle = programme.find('title').text
          except: sTitle = ""
          sPlotOutline = "sPlotOutline"
          try: sPlot = programme.find('desc').text
          except: sPlot = ""
          
          try:
            sOriginalTitle = "sOriginalTitle"
            titles = programme.findall('title')
            for title in titles:
              if title.get("language") == "xx":
                sOriginalTitle = title.text
          except: 
            sOriginalTitle = "sOriginalTitle"
          
          try: 
            sCast = programme.find("credits").find('actor').text
            #for actor in programme.find("credits").findall('actor'):
            #  sCast += actor.text + ", "
              
          except: sCast = "sCast"
          
          try: sDirector = programme.find("credits").find('director').text
          except: sDirector = ""
          try: sWriter = programme.find("credits").find('writer').text
          except: sWriter = ""
          try: iYear = programme.find('date').text
          except: iYear = 0
          
          sIMDBNumber = ""
          
          try: sIconPath = programme.find('icon').get("src")
          except: sIconPath = ""
          
          log(sTitle, 2)
          
          dts = programme.get('start')[:12]
          t = time.strptime(dts, "%Y%m%d%H%M")
          dt = datetime(*(t[:6]))
          iStartTime = int((dt - datetime(1970,1,1)).total_seconds())
          log("iStartTime %s" % iStartTime, 2)
          
          dts = programme.get('stop')[:12]
          log("dts %s " % dts)
          t = time.strptime(dts, "%Y%m%d%H%M")
          dt = datetime(*(t[:6]))
          iEndTime = int((dt - datetime(1970,1,1)).total_seconds())
          log("iEndTime %s" % iEndTime, 2)
          
          iGenreType = 256
          iGenreSubType = 0
          
          try: sGenre = programme.find("category").text
          except: sGenre = ""
          
          iFirstAired = 0
          iParentalRating = 12
          iSeriesId = 0
          iEpisodeId = 0
          iEpisodePart = 0
          sEpisodeName = ""
          
          try: iStarRating = programme.find('rating').find("value").text
          except: iStarRating = 0
          
          item = [i, idEpg, sTitle, sPlotOutline, sPlot,
                  sOriginalTitle, sCast, sDirector, sWriter, iYear,
                  sIMDBNumber, sIconPath, iStartTime, iEndTime, iGenreType, 
                  iGenreSubType, sGenre, iFirstAired, iParentalRating, iStarRating, 
                  bNotify, iSeriesId, iEpisodeId, iEpisodePart, sEpisodeName]
                  
          sql_command = """INSERT INTO epgtags (
                            iBroadcastUid,
                            idEpg,
                            sTitle,
                            sPlotOutline,
                            sPlot,
                            sOriginalTitle,
                            sCast,
                            sDirector,
                            sWriter,
                            iYear,
                            sIMDBNumber,
                            sIconPath,
                            iStartTime,
                            iEndTime,
                            iGenreType,
                            iGenreSubType,
                            sGenre,
                            iFirstAired,
                            iParentalRating,
                            iStarRating,
                            bNotify,
                            iSeriesId,
                            iEpisodeId,
                            iEpisodePart,
                            sEpisodeName
                        )
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);"""
                        
          cursor.execute(sql_command, item)
          conn.commit()
        except Exception as er:
          log(er, 4)
          pass
      #else:
      #  log("Skipping channel %s as its not in playlist" % channel)    
        
    log("Ended EPG parse for channel")

if progress_bar:
  progress_bar.close()