# YouTube Auto Uploader

<div align="center">

**Automatically upload gameplay videos to YouTube with ease**

[![GitHub release](https://img.shields.io/github/v/release/oHaruki/YouTubeUploaderElectron?style=flat-square)](https://github.com/oHaruki/YouTubeUploaderElectron/releases/latest)
[![License](https://img.shields.io/github/license/oHaruki/YouTubeUploaderElectron?style=flat-square)](LICENSE)
[![Ko-Fi](https://img.shields.io/badge/Support-Ko--fi-FF5E5B?style=flat-square&logo=ko-fi)](https://ko-fi.com/harukidev)

</div>

## Overview

YouTube Auto Uploader is a desktop application that automatically uploads gameplay videos to YouTube from a monitored folder. Perfect for content creators who want to streamline their workflow.

## Key Features

- **Automatic Uploads**: Monitors a folder and uploads new video files to YouTube
- **Customizable Metadata**: Set title templates, descriptions, tags, and privacy settings
- **Multiple API Projects**: Support for multiple YouTube API projects to overcome quota limits
- **Channel Selection**: Choose which YouTube channel to upload to
- **Modern Interface**: Clean UI with dark mode support

## Installation

1. Go to the [Releases page](https://github.com/oHaruki/YouTubeUploaderElectron/releases)
2. Download the latest zip file
3. Extract the zip file
4. Run the `YouTube Auto Uploader.exe` file

## Quick Start

1. Set up a YouTube API project and download credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project and enable YouTube Data API v3
   - Create OAuth credentials with redirect URI: `http://localhost:5000/oauth2callback`

2. Launch the app and authenticate with YouTube
3. Select a folder to monitor
4. Configure basic settings (title, description, privacy)
5. Click "Start Monitoring"

## Multiple API Projects

To overcome YouTube's daily upload limits, you can add multiple API projects in the "API Projects" tab. The application will automatically rotate between projects when limits are reached.

## Troubleshooting

- **Python Required**: Make sure Python is installed and in your PATH
- **Authentication**: Verify your OAuth credentials and redirect URIs
- **Logs**: Check logs in `%APPDATA%\youtube-auto-uploader\logs` (Windows) or `~/.youtube-auto-uploader/logs` (Mac/Linux)

## Support the Project

This application is completely free! If you find it helpful, please consider supporting its development:

[![Ko-Fi Support](https://img.shields.io/badge/Buy%20me%20a%20coffee-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/harukidev)

## License

MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Thanks to the YouTube Data API, Electron, Flask, and Bootstrap.