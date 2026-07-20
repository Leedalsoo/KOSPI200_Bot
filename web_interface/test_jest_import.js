try {
  const path = require.resolve('jest');
  console.log("Jest resolved path:", path);
} catch (e) {
  console.error("Failed to resolve Jest:", e);
}
