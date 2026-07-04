# V0.16.0
## Notes:
## Added:
### #15 - ADM Mode
First iteration of the Animation Desk Mode that let's you use the VOP as a background for physical animations in front of the projection screen. Can be used for cel-animations, cutouts, puppets/claymation. A lot of things. And as with other things in the VOP. It's needlessly realistic. So there's no undos. Once a frame is committed to the Cam Mag. It's committed. 
### Skip keyframe pairs that are 0 exposure time.
This is simply to speed up working on composites that need multiple passes but not all passes need to run through the whole exposure sheet. The mechanism detects keyframe pairs that are set to 0 as exposure time. If a keyframe is 0 as exposure time but a keyframe on either side of it, before or after, is not 0, that's a fade and that shouldn't be skipped. 
### Pi's status LED turn off during exposure
To minimize the risk of stray light reflecting off the projection screen, the status LED on the Pi will now turn off during exposures. 
## Changed:

## Fixed:
### The ONLINE indicator didn't work
fixed.
