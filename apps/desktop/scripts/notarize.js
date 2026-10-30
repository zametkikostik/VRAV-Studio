exports.default = async function notarizeMaybe(context) {
  const { electronPlatformName, appOutDir } = context;
  if (electronPlatformName !== "darwin") return;
  if (!process.env.APPLE_ID || !process.env.APPLE_APP_SPECIFIC_PASSWORD || !process.env.APPLE_TEAM_ID) {
    console.log("Skipping notarization (APPLE_* env not set)");
    return;
  }
  const appName = context.packager.appInfo.productFilename;
  const { notarize } = require("@electron/notarize");
  await notarize({
    appBundleId: "studio.vrav.app",
    appPath: `${appOutDir}/${appName}.app`,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
  });
};
