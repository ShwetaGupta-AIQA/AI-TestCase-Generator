/// <reference types="vitest/config" />
import {defineConfig} from 'vitest/config';
import {loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode})=>({plugins:[react()],server:{port:5173,strictPort:true,proxy:{'/api':{target:process.env.TESTGEN_API_PROXY||loadEnv(mode,process.cwd(),'').TESTGEN_API_PROXY||'http://127.0.0.1:8000',changeOrigin:true,rewrite:path=>path.replace(/^\/api/,'')}}},test:{environment:'jsdom',setupFiles:['./src/test-setup.ts']}}));
