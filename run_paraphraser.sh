#!/usr/bin/env bash
python3 ./train_model.py -t parlai_tasks.paraphrases.agents \
                         -m parlai_agents.paraphraser.paraphraser:ParaphraserAgent \
                         -mf /tmp/paraphraser_0 \
                         --datatype train:ordered \
                         --batchsize 256 \
                         --display-examples False \
                         --max-train-time -1 \
                         --num-epochs -1 \
                         --log-every-n-secs -1 \
                         --log-every-n-epochs 1 \
                         --learning_rate 0.0001 \
                         --hidden_dim 200 \
                         --validation-every-n-epochs 5 \
                         --fasttext_embeddings_dict "/tmp/paraphraser.emb" \
                         --fasttext_model '/tmp/ft_0.8.3_yalen_sg_300.bin' \
                         --cross-validation-seed 50 \
                         --cross-validation-model-index 0 \
                         --cross-validation-splits-count 5
##                         --pretrained_model '/tmp/paraphraser'
##                         --validation-patience 5 \

python3 ./train_model.py -t parlai_tasks.paraphrases.agents \
                         -m parlai_agents.paraphraser.paraphraser:EnsembleParaphraserAgent \
                         -mf /tmp/paraphraser \
                         --model_files /tmp/paraphraser \
                         --datatype test \
                         --batchsize 256 \
                         --display-examples False \
                         --fasttext_embeddings_dict "/tmp/paraphraser.emb" \
                         --fasttext_model '/tmp/ft_0.8.3_yalen_sg_300.bin' \
                         --cross-validation-splits-count 5