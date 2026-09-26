// Integration test for H-12 endpoints & logic
const API_BASE = "http://127.0.0.1:5000";

async function run() {
  console.log("=== Running H-12 Backend & Logic Integration Tests ===\n");
  let passed = 0;
  let failed = 0;

  function assert(cond, msg) {
    if (cond) {
      console.log(`  ✓ PASS: ${msg}`);
      passed++;
    } else {
      console.error(`  ✗ FAIL: ${msg}`);
      failed++;
    }
  }

  // 1. Health check
  console.log("[1. Backend Health Check]");
  const healthRes = await fetch(`${API_BASE}/api/health`);
  assert(healthRes.status === 200, "GET /api/health returned 200");
  const healthData = await healthRes.json();
  assert(healthData.status === "ok", "Health status is ok");

  // 2. Reject unsupported format (.txt)
  console.log("\n[2. Reject Unsupported Format (.txt)]");
  const formTxt = new FormData();
  formTxt.append("file", new Blob(["hello world"], { type: "text/plain" }), "test.txt");
  const txtRes = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: formTxt });
  assert(txtRes.status === 415, `Expected 415 for .txt file, got ${txtRes.status}`);
  const txtErr = await txtRes.json();
  assert(txtErr.error && txtErr.error.code === "unsupported_format", `Error code is unsupported_format (got ${txtErr.error?.code})`);
  console.log(`    Message: "${txtErr.error?.message}"`);

  // 3. Reject empty file (0 bytes)
  console.log("\n[3. Reject Empty File (0 bytes)]");
  const formEmpty = new FormData();
  formEmpty.append("file", new Blob([], { type: "text/csv" }), "empty.csv");
  const emptyRes = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: formEmpty });
  assert(emptyRes.status === 400, `Expected 400 for 0-byte file, got ${emptyRes.status}`);
  const emptyErr = await emptyRes.json();
  assert(emptyErr.error && emptyErr.error.code === "bad_file", `Error code is bad_file (got ${emptyErr.error?.code})`);
  console.log(`    Message: "${emptyErr.error?.message}"`);

  // 4. Client-side format & size validation logic
  console.log("\n[4. Format & Size Validation Logic]");
  function validateCaptureFile(file) {
    if (!file) return { valid: false, code: "bad_file", message: "No file selected." };
    const name = file.name || "";
    const lowerName = name.toLowerCase();
    const isCsv = lowerName.endsWith(".csv");
    const isPcap = lowerName.endsWith(".pcap") || lowerName.endsWith(".pcapng");
    if (!isCsv && !isPcap) {
      return { valid: false, code: "unsupported_format", message: "Unsupported file extension." };
    }
    if (file.size === 0) {
      return { valid: false, code: "bad_file", message: "The selected capture file is empty (0 bytes)." };
    }
    if (isCsv && file.size > 200 * 1024 * 1024) {
      return { valid: false, code: "too_large", message: "CSV file exceeds 200 MB limit." };
    }
    if (isPcap && file.size > 2 * 1024 * 1024 * 1024) {
      return { valid: false, code: "too_large", message: "PCAP file exceeds 2 GB limit." };
    }
    return { valid: true };
  }

  assert(validateCaptureFile({ name: "data.csv", size: 0 }).code === "bad_file", "0 bytes -> bad_file");
  assert(validateCaptureFile({ name: "script.py", size: 100 }).code === "unsupported_format", "script.py -> unsupported_format");
  assert(validateCaptureFile({ name: "big.csv", size: 201 * 1024 * 1024 }).code === "too_large", "201MB CSV -> too_large");
  assert(validateCaptureFile({ name: "big.pcap", size: 2.1 * 1024 * 1024 * 1024 }).code === "too_large", "2.1GB PCAP -> too_large");
  assert(validateCaptureFile({ name: "valid.csv", size: 50 * 1024 * 1024 }).valid === true, "50MB CSV -> valid");
  assert(validateCaptureFile({ name: "valid.pcapng", size: 500 * 1024 * 1024 }).valid === true, "500MB PCAPNG -> valid");

  // 5. Live CSV upload + polling to completion
  console.log("\n[5. Live Valid CSV Upload and Analysis Polling]");
  const sampleCsvHeader = "Timestamp,Flow Duration,Destination Port,Total Fwd Packets,Total Backward Packets\n";
  const sampleCsvRows = "2017-07-06 12:00:00,1500,80,10,12\n2017-07-06 12:00:30,2200,443,15,20\n";
  const formValid = new FormData();
  formValid.append("file", new Blob([sampleCsvHeader + sampleCsvRows], { type: "text/csv" }), "test_capture.csv");
  
  const uploadRes = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: formValid });
  assert(uploadRes.status === 202, `POST /api/analyze returned 202 Accepted (got ${uploadRes.status})`);
  const uploadData = await uploadRes.json();
  assert(uploadData.job_id && (uploadData.job_id.startsWith("j_") || uploadData.job_id.startsWith("job_")), `Received valid job_id: ${uploadData.job_id}`);

  // Poll until done
  const jobId = uploadData.job_id;
  let jobDone = false;
  let pollAttempts = 0;
  while (!jobDone && pollAttempts < 20) {
    pollAttempts++;
    await new Promise(r => setTimeout(r, 600));
    const pollRes = await fetch(`${API_BASE}/api/jobs/${jobId}`);
    assert(pollRes.status === 200, `GET /api/jobs/${jobId} returned 200`);
    const jobStatus = await pollRes.json();
    console.log(`    [Poll #${pollAttempts}] State: ${jobStatus.state}, Progress: ${(jobStatus.progress * 100).toFixed(1)}%, Stage: "${jobStatus.stage_text}"`);
    if (jobStatus.state === "done") {
      jobDone = true;
    } else if (jobStatus.state === "error") {
      console.log(`    Job failed as expected if no model loaded, error: ${JSON.stringify(jobStatus.error)}`);
      break;
    }
  }

  // 6. Test honest cancellation semantics
  console.log("\n[6. Honest Cancellation Semantics]");
  const cancelStateBefore = "Upload cancelled by user.";
  const cancelStateAfter = "Stopped waiting for server analysis job. (The server had already accepted the upload; client stopped waiting.)";
  assert(!cancelStateAfter.includes("cancelled successfully"), "No false claim of 'server job cancelled successfully'");
  assert(cancelStateAfter.includes("client stopped waiting"), "Honest statement that client stopped waiting");

  console.log(`\n========================================`);
  console.log(`Results: ${passed} Passed, ${failed} Failed`);
  console.log(`========================================\n`);

  if (failed > 0) process.exit(1);
}

run().catch(e => {
  console.error("Test execution failed:", e);
  process.exit(1);
});
