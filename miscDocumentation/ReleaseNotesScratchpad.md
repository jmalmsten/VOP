# v26.1.3

## Notes: 
The second release since the big move to GitHub.

## Added:
### #247 - Full Screen preview window
Pressing the full screen button for the preview screen should now make that section full screen. By using this, it's now possible to simply open a new browser window with the VOP GUI, move it to another screen and hit the full screen button. That gives you a full screen preview. And it also updates when the main window updates. Both on main page and on calibration page. 

### Separator of Pages and ADM mode toggle
Added a little separator to make it more obvious that the ADM mode toggle is a toggle not a full page. 

### Expanding the above full screen preview button to the Sheets area as well.

### Screen timeout
To save on the screens lifetime and processing cycles. A screen timeout has been added that will turn off the screen after 15 minutes of inactivity (1 min during initial testing) and also freeze the idle animation so it doesn't waste energy on frames that aren't being shown anywhere. 

## Changed:

### Fixing layout
rearranged a few of the sections to better use the screen real estate. 


## Fixed:

### Narrow browser window hides preview area. 
When doing the layout changes above. It looks fine on 16:9 1080p screens. But when narrower screens are used. The previw area gets cut off and eventually hidden completely off-screen. 

### Silencing redundant logs
When adding the screen timeout I found that the journalctl is spammed with redundant lines where ddcutil tries to find a desktop and there of course is none. So I silenced those logs with a -q flags so they don't clutter up the logs. 