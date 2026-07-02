<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# Native client builds

The client UI is still the single HTML5/PWA frontend in `frontend/`. Native
clients wrap that same UI so Android, iOS, macOS, Windows, and browser users
share one interface and one REST API.

## Build bundle

Set the API origin that the installed app should call:

```sh
export HCP_API_BASE="https://study.example.edu"
make client-bundle
```

This writes `clients/native/www/` and injects `frontend/client-config.js` with
the configured API base. Browser deployments leave `apiBase` empty because the
frontend and API are served from the same origin.

## Android

Install Node.js, Android Studio, and the Android SDK. Then:

```sh
cd clients/native
npm install
npm run android:add      # first time only
HCP_API_BASE=https://study.example.edu npm run android:sync
npm run android:open
```

Use Android Studio to set signing keys and build an APK/AAB. The convenience
`npm run android:build` invokes Gradle after sync, but release signing should be
configured in Android Studio or CI secrets.

## iOS

Builds require macOS and Xcode:

```sh
cd clients/native
npm install
npm run ios:add          # first time only
HCP_API_BASE=https://study.example.edu npm run ios:sync
npm run ios:open
```

Use Xcode to select the Apple Developer Team, signing identity, bundle version,
and App Store/TestFlight distribution target.

## macOS DMG

Install Node.js, Rust, and Xcode Command Line Tools. DMG installers are for
macOS desktop apps. They are separate from iOS apps, which are distributed
through Xcode/TestFlight/App Store instead of `.dmg`.

Build Apple Silicon:

```sh
cd clients/native
npm install
rustup target add aarch64-apple-darwin
HCP_API_BASE=https://study.example.edu npm run macos:build:silicon
```

Build Intel:

```sh
cd clients/native
npm install
rustup target add x86_64-apple-darwin
HCP_API_BASE=https://study.example.edu npm run macos:build:intel
```

Build a universal DMG when both targets are installed:

```sh
cd clients/native
npm install
rustup target add aarch64-apple-darwin x86_64-apple-darwin
HCP_API_BASE=https://study.example.edu npm run macos:build:universal
```

The generated `.dmg` files are written below
`clients/native/src-tauri/target/<target>/release/bundle/dmg/`. Production
distribution should use Apple Developer ID signing and notarization.

## Windows

The Windows desktop shell uses Tauri. Install Node.js and Rust, then on Windows:

```sh
cd clients/native
npm install
HCP_API_BASE=https://study.example.edu npm run windows:build
```

The checked-in Tauri configuration targets MSI and NSIS installers. Production
builds should use a real Windows code-signing certificate and timestamp server.

## Security notes

- Native clients still require HTTPS API endpoints.
- Tokens, nonces, TLS, and certificate validation remain server-enforced.
- Do not embed private keys, administrator secrets, SMTP credentials, or API
  signing material in the client bundle.
- Mobile microphone/file permissions are requested by the WebView at runtime.
