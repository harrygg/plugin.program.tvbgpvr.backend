# -*- coding: utf-8 -*-
import os
import xbmc
import urllib
import xbmcgui
from resources.lib.utils import *
from resources.lib.playlist import *

# #append_pydev_remote_debugger
# if os.environ.get('PVRDEBUG'):
  # sys.path.append(os.environ['PYSRC'])
  # import pydevd
  # pydevd.settrace('127.0.0.1', stdoutToServer=False, stderrToServer=False)
# #end_append_pydev_remote_debugger	

log("Started on %s" % user_agent)
if scheduled_run:
  log(translate(32004))
  
### If addon is started manually or is in debug mode, display the progress bar 
if not scheduled_run or settings.debug:
  progress_bar = xbmcgui.DialogProgressBG()
  progress_bar.create(heading=this.getAddonInfo('name'))

try:
  # Initialize the playlsit object
  pl = Playlist(location=get_location(),
                log=log, 
                user_agent=user_agent, 
                progress=progress_bar,
                groups_from_progider=settings.groups_from_progider,
                temp_folder=profile_dir,
                mapping_file=mapping_file)
  
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
      pl.save(path=os.path.join(settings.copy_to_folder, pl_name))

except Exception, er:
  log(er, xbmc.LOGERROR)

### Schedule next run
interval = int(settings.run_on_interval) * 60
log(translate(32007) % interval)
command = "AlarmClock('ScheduledReload', %s, %s, silent)" % (RUNSCRIPT, interval)
xbmc.executebuiltin(command)

if progress_bar:
  progress_bar.close()
