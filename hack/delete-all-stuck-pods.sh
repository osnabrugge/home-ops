#!/usr/bin/env bash

function delete_stuckpods () {
    echo "Deleting stuck pods in namespace $1"
    kubectl get pods -n $1 | grep Evicted | awk '{print $1}' | xargs kubectl delete pod -n $1
}

STUCK_NS=$(kubectl get ns | awk '$2=="Evicted" {print $1}')

for ns in $STUCK_NS
do
    delete_stuckpods $ns
done
