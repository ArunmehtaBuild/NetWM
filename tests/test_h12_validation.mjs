import { ApiClient } from "../frontend/js/api.js";

async function runTests() {
  console.log("=== NetWM H-12 Test Suite ===");
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

  const api = new ApiClient();

  // Test 1: File format & size validations
  console.log("\n[Test Group 1: Client-side Validation Rules]");
  const emptyFile = { name: "empty.csv", size: 0 };
  const valEmpty = api.validateCaptureFile(emptyFile);
  assert(!valEmpty.valid && valEmpty.code === "bad_file", "0-byte file rejected as bad_file");

  const txtFile = { name: "test.txt", size: 1024 };
  const valTxt = api.validateCaptureFile(txtFile);
  assert(!valTxt.valid && valTxt.code === "unsupported_format", "Invalid extension .txt rejected as unsupported_format");

  const exeFile = { name: "payload.exe", size: 50000 };
  const valExe = api.validateCaptureFile(exeFile);
  assert(!valExe.valid && valExe.code === "unsupported_format", "Invalid extension .exe rejected as unsupported_format");

  const largeCsv = { name: "big.csv", size: 201 * 1024 * 1024 };
  const valLargeCsv = api.validateCaptureFile(largeCsv);
  assert(!valLargeCsv.valid && valLargeCsv.code === "too_large", "CSV > 200MB rejected as too_large");

  const validCsv = { name: "normal.csv", size: 5 * 1024 * 1024 };
  const valValidCsv = api.validateCaptureFile(validCsv);
  assert(valValidCsv.valid, "Valid CSV 5MB passes validation");

  const largePcap = { name: "big.pcap", size: 2.1 * 1024 * 1024 * 1024 };
  const valLargePcap = api.validateCaptureFile(largePcap);
  assert(!valLargePcap.valid && valLargePcap.code === "too_large", "PCAP > 2GB rejected as too_large");

  const validPcap = { name: "capture.pcap", size: 50 * 1024 * 1024 };
  const valValidPcap = api.validateCaptureFile(validPcap);
  assert(valValidPcap.valid, "Valid PCAP 50MB passes validation");

  const validPcapng = { name: "capture.pcapng", size: 50 * 1024 * 1024 };
  const valValidPcapng = api.validateCaptureFile(validPcapng);
  assert(valValidPcapng.valid, "Valid PCAPNG 50MB passes validation");

  // Test 2: Mock mode progress & cancellation
  console.log("\n[Test Group 2: Mock Mode Upload & Progress & Cancellation]");
  const mockApi = new ApiClient();
  mockApi.useMock = true;

  const mockProgressEvents = [];
  const mockPromise = mockApi.uploadCapture(validCsv, (prog) => {
    mockProgressEvents.push(prog);
  });

  // Let it start, then cancel
  await new Promise(r => setTimeout(r, 100));
  const wasCancelled = mockApi.cancelUpload();
  assert(wasCancelled, "Mock upload cancellation triggered");

  try {
    await mockPromise;
    assert(false, "Mock upload should have rejected upon cancel");
  } catch (err) {
    assert(err.code === "cancelled", `Mock upload cancelled with code 'cancelled' (got '${err.code}')`);
  }

  // Test 3: Full Mock mode completion
  console.log("\n[Test Group 3: Full Mock Mode Upload Completion]");
  const mockApiFull = new ApiClient();
  mockApiFull.useMock = true;
  const fullEvents = [];
  const fullResult = await mockApiFull.uploadCapture(validCsv, (prog) => {
    fullEvents.push(prog);
  });
  assert(fullResult && fullResult.isMock === true, "Full mock upload returned payload with isMock=true");
  assert(fullEvents.length >= 6, `Progress emitted ${fullEvents.length} events`);
  assert(fullEvents[0].state === "uploading", "Initial state is 'uploading'");
  assert(fullEvents[fullEvents.length - 1].state === "done", "Final state is 'done'");

  console.log(`\nResults: ${passed} Passed, ${failed} Failed`);
  if (failed > 0) process.exit(1);
}

runTests().catch(e => {
  console.error("Test runner failed:", e);
  process.exit(1);
});
