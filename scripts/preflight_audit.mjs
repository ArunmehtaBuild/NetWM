// Preflight audit for H-15 Live Demo Rehearsal

async function preflight() {
  console.log("=== Preflight Audit for H-15 Rehearsal ===\n");
  
  // 1. /api/model
  console.log("1. Checking /api/model:");
  const modelRes = await fetch("http://127.0.0.1:5000/api/model");
  console.log("   Status:", modelRes.status);
  const modelData = await modelRes.json();
  console.log("   Model Name:", modelData.model_name);
  console.log("   Checkpoint:", modelData.checkpoint);
  console.log("   Train Days:", modelData.train_days);
  console.log("   Test Day:", modelData.test_day);
  console.log("   Metrics:", JSON.stringify(modelData.metrics, null, 2));

  // 2. /api/demos
  console.log("\n2. Checking /api/demos:");
  const demosRes = await fetch("http://127.0.0.1:5000/api/demos");
  const demos = await demosRes.json();
  console.log("   Demos count:", demos.length);
  demos.forEach(d => {
    console.log(`   - ID: ${d.id} | Day: ${d.day} | Flows: ${d.flows} | Windows: ${d.windows} | In-sample: ${d.in_sample}`);
  });

  // 3. /api/analyze/demo/thursday_infiltration
  console.log("\n3. Dispatching demo thursday_infiltration:");
  const demoPost = await fetch("http://127.0.0.1:5000/api/analyze/demo/thursday_infiltration", { method: "POST" });
  const { job_id } = await demoPost.json();
  console.log("   Job ID:", job_id);

  // Poll until done
  let job;
  while (true) {
    await new Promise(r => setTimeout(r, 400));
    const jobRes = await fetch(`http://127.0.0.1:5000/api/jobs/${job_id}`);
    job = await jobRes.json();
    if (job.state === "done" || job.state === "error") break;
  }
  console.log(`   Job completed: state=${job.state}, progress=${job.progress}`);

  // 4. Get result
  const resRes = await fetch(`http://127.0.0.1:5000/api/jobs/${job_id}/result`);
  const payload = await resRes.json();
  console.log("\n4. Result Payload Audit:");
  console.log("   Source:", payload.source);
  console.log("   Timeline length:", payload.timeline ? payload.timeline.length : 0);
  console.log("   Model info:", payload.model);
  console.log("   Total alarms:", payload.timeline ? payload.timeline.filter(w => w.alarm).length : 0);
  console.log("   in_sample field:", payload.in_sample);

  // 5. Inspect specific timestamp windows mentioned in demo script
  console.log("\n5. Inspecting Script-Specific Timestamps in Timeline:");
  if (payload.timeline && payload.timeline.length > 0) {
    const t0 = payload.timeline[0];
    const tEnd = payload.timeline[payload.timeline.length - 1];
    console.log(`   First window [idx 0]: ts=${t0.ts}, p_max=${t0.p_max}, surprise=${t0.surprise}`);
    console.log(`   Last window [idx ${payload.timeline.length - 1}]: ts=${tEnd.ts}, p_max=${tEnd.p_max}, surprise=${tEnd.surprise}`);

    // Print all windows with alarms
    console.log("\n   All Alarmed Windows in Slice:");
    payload.timeline.forEach((w, idx) => {
      if (w.alarm) {
        console.log(`     - idx ${idx} | ts: ${w.ts} | p_max: ${w.p_max} | surprise: ${w.surprise} | pred_stage: ${w.pred_stage} | true_stage: ${w.true_stage}`);
      }
    });

    // Key timestamps
    console.log("\n   Key Script Target Windows:");
    const timesToFind = ["17:00", "17:10", "17:19", "17:33", "18:04", "18:23", "18:45"];
    timesToFind.forEach(target => {
      const matchIdx = payload.timeline.findIndex(w => (w.ts || "").includes(target));
      if (matchIdx >= 0) {
        const w = payload.timeline[matchIdx];
        const talkers = (w.top_talkers || []).slice(0, 3).map(t => `${t.ip} (${t.flows} flows)`).join(", ");
        console.log(`   Target ~${target} [idx ${matchIdx}]: ts=${w.ts} | p_max=${w.p_max} | surprise=${w.surprise} | alarm=${w.alarm} | pred_stage=${w.pred_stage} | talkers: [${talkers}]`);
      } else {
        console.log(`   Target ~${target}: not found by direct substring.`);
      }
    });

    // Calculate surprise statistics
    const benignSurprises = payload.timeline.filter(w => !w.true_stage || w.true_stage === 0).map(w => w.surprise || 0);
    benignSurprises.sort((a, b) => a - b);
    const medianBenign = benignSurprises[Math.floor(benignSurprises.length / 2)];
    console.log(`\n   Surprise Statistics:`);
    console.log(`   - Median Benign Surprise: ${medianBenign}`);
    const maxSurprise = Math.max(...payload.timeline.map(w => w.surprise || 0));
    console.log(`   - Max Surprise in slice: ${maxSurprise}`);
  }
}

preflight().catch(e => console.error("Preflight audit error:", e));
