# Logging

To take logs, you need to create the journal directory and give it the right permissions:
```
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo systemctl restart systemd-journald
```

Then, you can view the logs with:
```
journalctl -b -1 -k
```

Once you have identified your problem, you should deactivate logging to save the SD card from unnecessary writes: 
```
sudo rm -rf /var/log/journal
sudo systemctl restart systemd-journald
```