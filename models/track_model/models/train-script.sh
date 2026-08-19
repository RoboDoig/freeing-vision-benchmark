#!/bin/bash
sleap train --config-name single_instance.yaml --config-dir . 'trainer_config.ckpt_dir="models"' 'trainer_config.run_name="track_cam.single_instance.n=18"' 
