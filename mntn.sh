#run TNO North topology
cd /home/${USER}
sudo mn --custom /home/${USER}/coco_scripts/mdcoco2.py --topo tnonorth --controller remote,127.0.0.1
