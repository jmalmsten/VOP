# v26.2.7

## Notes: 
The second release since the big move to GitHub. 

I have now gotten into the habit of marking changes with the patch number so it's easier to keep track of what happened when between releases. 

If you noticed that things jumped from v26.1.3 to 26.2.4 without a release. It's because I realized I messed up in my philosopy for the version numbering. From now on. Once A release is made, like for v26.1.x, the release number gets bumped for subsequent patches. And The patches get numbered v26.2.1 and so on. This means that the release on GitHub is made with the latest patches and won't get new patches afterwards. So the next release will be something like v26.2.15 or something. I don't know exactly when. I don't have a set in stone release cycle for this repo. 

## Added:
### Patch 1: #247 - Full Screen preview window
Pressing the full screen button for the preview screen should now make that section full screen. By using this, it's now possible to simply open a new browser window with the VOP GUI, move it to another screen and hit the full screen button. That gives you a full screen preview. And it also updates when the main window updates. Both on main page and on calibration page. 

### Patch 1: Separator of Pages and ADM mode toggle
Added a little separator to make it more obvious that the ADM mode toggle is a toggle not a full page. 

### Patch 1: Expanding the above full screen preview button to the Sheets area as well.

### Patch 2: Screen timeout
To save on the screens lifetime and processing cycles. A screen timeout has been added that will turn off the screen after 15 minutes of inactivity (1 min during initial testing) and also freeze the idle animation so it doesn't waste energy on frames that aren't being shown anywhere. Just interact with the webGUI to unsuspend it. 

### Patch 3: webGUI now has a suspended state.
When screen goes into timeout, there's now a third state, color coded yellow, to show that the screen output has been suspended. 

## Changed:

### Patch 1: Fixing layout
rearranged a few of the sections to better use the screen real estate. 

### Patch 5: Moving ADM toggle
I realized that if it's hard for me to remember that the `ADM` button is not a page, but a toggle... It's downright impossible for those outside my head to know this as well. So I have now moved it from the row of pages to the row under the `EXECUTE SEQUENCE` button and made it into a regular checkbox to make it more clear what it does and it also makes more sense to have it near where the buttons for `ADM` will appear anyway.  

### Patch 8: Moving Defect Mapping buttons
Moved the Defect Mapping buttons so it's underneath the rest of the white balance bits. 

## Fixed:

### Patch 1: Narrow browser window hides preview area. 
When doing the layout changes above. It looks fine on 16:9 1080p screens. But when narrower screens are used. The previw area gets cut off and eventually hidden completely off-screen. This has been adjusted to fix it. 

### Patch 2: Silencing redundant logs
When adding the screen timeout I found that the journalctl is spammed with redundant lines where ddcutil tries to find a desktop and there of course is none. So I silenced those logs with a -q flags so they don't clutter up the logs. 

#### Edit: this turned out to break things so the silencing has been redacted for now with Patch 3.

### Patch 3: Fixing the screen timeout
Turned out the implementation of the screen timeout was a bit naive. So I have done the screen timeout a bit differently now. 

### Patch 4: Narrow viewport fix and fit_z fix
To make the webGUI more usable on narrow viewports like phones. I had to add in a little css to rearrange the buttons for the mags. Shouldn't change layout on the desktop view in full HD screens. 

fit_z also was still not fixed. Went ahead and did that. 

### Patch 6: General comment cleanup
As the repo has moved from codeberg to github. And issue numbers don't match. I have elected to try to clean out all the issue numbers that are referenced in the codebase comments. I have also tried to remove other cryptic references that can't be deduced with information that is in the codebase itself or a wiki page. All to make it less confusing for people outside my head to navigate the codebase. 

### Patch 6: removed instructions.md
Since alignment and focus is done in the webGUI that file was now deemed redundant.

### Patch 7: Fixed unused admClear()
During cleanup in Patch 6 I found that admClear() was not actually used anywhere and the button that should call it was not used either. Should be fixed now. 