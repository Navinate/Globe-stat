import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Single self-contained index.html: works on any static host and as a Claude artifact.
export default defineConfig({ plugins: [react(), viteSingleFile()] });
