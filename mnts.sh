#run TNO South topology
cd /home/${USER}
sudo mn --custom /home/${USER}/coco_scripts/mdcoco2.py --topo tnosouth --controller remote,127.0.0.1
