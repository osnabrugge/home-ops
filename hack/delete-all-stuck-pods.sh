#!/usr/bin/env bash

kubectl get po | grep -v Running | awk 'NR>1 {print $1}' | xargs kubectl delete po --force --grace-period=0