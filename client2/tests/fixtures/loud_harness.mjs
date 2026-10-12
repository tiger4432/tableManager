// A harness that says more than the 1 MiB spawnSync reads by default, then its verdict (read_harness_harness).
const line = `${'x'.repeat(99)}\n`;
process.stdout.write(line.repeat(12000));
console.log('ASSERTIONS 1 0');
