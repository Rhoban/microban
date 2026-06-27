# Cloning the SD card

First, go to gnome disks and create an image of the SD card.

Then, run the following commands to shrink the image. The `-Z` flag also compresses
the shrunk image with `xz`, which is what makes a ~4 GB raw image fit in a few
hundred MB for distribution. The `-a` flag runs the compression in parallel across
all CPU cores — much faster than the default single-threaded `xz`:
```
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh
sudo ./pishrink.sh -aZ ~/Documents/microban.img
```

This produces `~/Documents/microban.img.xz`. Check the final size with:
```
ls -lh ~/Documents/microban.img.xz
```
