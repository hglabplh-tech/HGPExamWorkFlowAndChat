// Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.hcpxmlworkflowchat.client',
  appName: 'HcpXmlWorkflowChat',
  webDir: 'www',
  bundledWebRuntime: false,
  server: {
    androidScheme: 'https',
    iosScheme: 'https'
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1000,
      backgroundColor: '#17233b',
      showSpinner: false
    }
  }
};

export default config;
