# V26.1.0

## Notes: 
First release since the big move from Codeberg to GitHub. With it also came the big change of calendar versioning. So we're now jumping straight from v0.16.x to the far flung future of v26.1.0. Just as a reminder. This just means that the first digits are the year, second is release number and third is a patch. Does having only two digits not mean that we're in trouble by the time it rolls over to year 2100? Yes. But that's a future relative's problem. And easily solved by then by just bumping the year value to four digits. 

## Added:

### Discussion forum
One unexpected bonus of this move is that I and others now have access to the Discussions page of the repo. Here things can be discussed more informally without necessarily making issues for everything. There's apparently also a "Show and tell" category here. Seems fun. Will see what happens here.

## Changed:

### Calendar Versioning.
As I never had a real clue as to what constituted a v1. I just kept pushing it ahead of myself. I realized that for a tool like the VOP. I might as well just change it to Calendar Versioning so that it's clear when it was released and wether it's just a patch or a full release number. 

### #240 - Rewrite of scripts to make sure they don't point to codeberg
As the codebase and documentation on the original codeberg repo will becoming obsolete fast. I'm repointig everything to the github counterparts. Should be no change for end users. But I want it noted.

## Fixed:

### Predeploy didn't accept pub-key path
Fixed this so predeploy goes smoother.

### Dead Pixel mapping moved back to calibration page
Since it's not a procedure that will be thought of for every pass, it lives better in the calibration page and it also fixes an issue where the output of the noise crusher measurement gets covered by the dead pixel mapper buttons.