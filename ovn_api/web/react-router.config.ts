import type { Config } from '@react-router/dev/config';

export default {
	appDirectory: './src/app',
	serverBuildFile: 'assets/server-build.js',
	ssr: true,
	prerender: ['/*?'],
} satisfies Config;
