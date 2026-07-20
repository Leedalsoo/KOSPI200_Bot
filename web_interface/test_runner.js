const jest = require('jest');
const fs = require('fs');

const options = {
  projects: [__dirname],
  verbose: true,
  runInBand: true,
  silent: false
};

console.log("Starting Jest programmatically...");
jest.runCLI(options, options.projects)
  .then((result) => {
    const summary = result.results.success ? "SUCCESS" : "FAILED";
    console.log(`Jest Finished with status: ${summary}`);
    
    const report = {
      success: result.results.success,
      numTotalTests: result.results.numTotalTests,
      numPassedTests: result.results.numPassedTests,
      numFailedTests: result.results.numFailedTests,
      testResults: result.results.testResults.map(tr => ({
        testFilePath: tr.testFilePath,
        failureMessage: tr.failureMessage,
        skipped: tr.skipped
      }))
    };
    fs.writeFileSync('jest_js_report.json', JSON.stringify(report, null, 2), 'utf8');
    
    if (!result.results.success) {
      process.exit(1);
    }
  })
  .catch((err) => {
    console.error("Execution Error:", err);
    fs.writeFileSync('jest_js_error.log', err.stack || err.toString(), 'utf8');
    process.exit(1);
  });
