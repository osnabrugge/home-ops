#!/usr/bin/env node

/**
 * Kubernetes Cluster Health Snapshot
 *
 * Quick diagnostic tool for cluster health checks
 * Usage: node k8s-observability-server.js [command]
 */

const { exec } = require('child_process');
const { promisify } = require('util');
const fs = require('fs');
const path = require('path');

const execAsync = promisify(exec);

async function runCmd(cmd) {
  try {
    const { stdout, stderr } = await execAsync(cmd, { maxBuffer: 10 * 1024 * 1024 });
    return { success: true, output: stdout.trim(), error: null };
  } catch (error) {
    return { success: false, output: null, error: error.message };
  }
}

async function nodeStatus() {
  console.log('\n=== NODE STATUS ===');
  const { output } = await runCmd('kubectl get nodes -o wide');
  console.log(output || '(no output)');
}

async function podStatus() {
  console.log('\n=== POD STATUS (Failed/Pending) ===');
  const { output } = await runCmd("kubectl get pods -A | grep -E 'CrashLoop|Pending|ImagePull|Error' || echo 'All pods healthy'");
  console.log(output || '(no output)');
}

async function helmStatus() {
  console.log('\n=== HELM RELEASES ===');
  const { output } = await runCmd('kubectl get helmreleases -A --sort-by=.status.lastAppliedTime | tail -20');
  console.log(output || '(no output)');
}

async function recentEvents() {
  console.log('\n=== RECENT ERRORS/WARNINGS (Last 30min) ===');
  const { output } = await runCmd("kubectl get events -A --since=30m | grep -E 'Warning|Error|Failed' || echo 'No recent warnings'");
  console.log(output || '(no output)');
}

async function alerts() {
  console.log('\n=== ACTIVE ALERTS ===');
  try {
    const { output } = await runCmd('kubectl get alertmanageralerts -A 2>/dev/null || echo "Alertmanager not accessible"');
    console.log(output || '(no output)');
  } catch {
    console.log('(Alertmanager query failed)');
  }
}

async function fullHealthSnapshot() {
  console.log('╔═══════════════════════════════════════╗');
  console.log('║  KUBERNETES CLUSTER HEALTH SNAPSHOT   ║');
  console.log(`║  ${new Date().toISOString().slice(0, 19)}              ║`);
  console.log('╚═══════════════════════════════════════╝');

  await nodeStatus();
  await podStatus();
  await helmStatus();
  await recentEvents();
  await alerts();

  console.log('\n✓ Snapshot complete\n');
}

// Export for programmatic use
module.exports = {
  nodeStatus,
  podStatus,
  helmStatus,
  recentEvents,
  alerts,
  fullHealthSnapshot,
  runCmd,
};

// CLI usage
if (require.main === module) {
  const command = process.argv[2] || 'full';

  switch (command) {
    case 'nodes':
      nodeStatus().catch(console.error);
      break;
    case 'pods':
      podStatus().catch(console.error);
      break;
    case 'helm':
      helmStatus().catch(console.error);
      break;
    case 'events':
      recentEvents().catch(console.error);
      break;
    case 'alerts':
      alerts().catch(console.error);
      break;
    case 'full':
      fullHealthSnapshot().catch(console.error);
      break;
    default:
      console.log(`Usage: node k8s-observability-server.js [command]
Commands:
  nodes   - Node status
  pods    - Pod status (failed/pending only)
  helm    - HelmRelease status
  events  - Recent errors/warnings
  alerts  - Active alerts
  full    - Complete health snapshot (default)`);
  }
}
