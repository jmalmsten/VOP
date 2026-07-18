# V0.16
## Notes:
## Added:
### #15 - ADM Mode
First iteration of the Animation Desk Mode that let's you use the VOP as a background for physical animations in front of the projection screen. Can be used for cel-animations, cutouts, puppets/claymation. A lot of things. And as with other things in the VOP. It's needlessly realistic. So there's no undos. Once a frame is committed to the Cam Mag. It's committed. 
### Skip keyframe pairs that are 0 exposure time.
This is simply to speed up working on composites that need multiple passes but not all passes need to run through the whole exposure sheet. The mechanism detects keyframe pairs that are set to 0 as exposure time. If a keyframe is 0 as exposure time but a keyframe on either side of it, before or after, is not 0, that's a fade and that shouldn't be skipped. 
### Pi's status LED turn off during exposure
To minimize the risk of stray light reflecting off the projection screen, the status LED on the Pi will now turn off during exposures. 
### #230 - Sweep Mode
This is a dropdown menu for each projection side image that makes it do brightness sweeps across the image. It defaults to ByPass to make sure it doesn't do anything weird unless you want it. Other modes are: 
- **HighPass** - This makes all the brightness values above the threshold white and all below dark
- **LowPass** - This does the opposite
- **Bandpass** - This makes values above and below the threshold black and only the threshold value white.

Along with these is the **Width** value. This widens the values at the threshold to show more or less pixels. 

This mode runs a filter sweep during a smear exposure. You can use these with other projection layers to produce some wild pseudo-3D renderings. And even do almost depth compositing by rendering out from a 3D modeling program like Blender, 2 passes, Depth Map and a Beauty Pass. Depth to provide where the pixels are in 3D space and Beauty Pass to provide the colors of those pixels. And you'll use the depth map to tell which pixels should be in what depth using the Sweep mode. I imagine one can use this to make warp speed stretching like effects from the Star Trek TNG shows. 

Other, more abstract use-cases are of course possible. But that's the most practical one I can think of right now. 

## Changed:

## Fixed:
### The ONLINE indicator didn't work
fixed.
