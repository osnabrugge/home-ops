# Frigate


## nvidia detector with k3s/containerd
- Use [nerdctrl](https://github.com/containerd/nerdctl) in place of docker run for containerd when generating tensorrt models.

```sh
sudo nerdctl run --gpus=all --rm -it -v `pwd`/trt-models:/tensorrt_models -v `pwd`/tensorrt_models.sh:/tensorrt_models.sh nvcr.io/nvidia/tensorrt:22.07-py3 /tensorrt_models.sh
```
