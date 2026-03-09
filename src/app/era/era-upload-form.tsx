"use client";

import { useState } from "react";

type UploadState = {
  status: "idle" | "submitting" | "success" | "error";
  message: string | null;
  payload: string | null;
};

const INITIAL_STATE: UploadState = {
  status: "idle",
  message: null,
  payload: null,
};

export function EraUploadForm() {
  const [state, setState] = useState<UploadState>(INITIAL_STATE);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = event.currentTarget;
    const formData = new FormData(form);

    if (!formData.get("file")) {
      setState({
        status: "error",
        message: "Select an ERA file before submitting.",
        payload: null,
      });
      return;
    }

    setState({
      status: "submitting",
      message: "Uploading ERA file...",
      payload: null,
    });

    try {
      const response = await fetch("/api/era", {
        method: "POST",
        body: formData,
      });
      const contentType = response.headers.get("content-type") ?? "";
      const payload = contentType.includes("application/json")
        ? JSON.stringify(await response.json(), null, 2)
        : await response.text();

      setState({
        status: response.ok ? "success" : "error",
        message: response.ok ? "Upload completed." : `Upload failed with status ${response.status}.`,
        payload,
      });

      if (response.ok) {
        form.reset();
      }
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "Unable to submit ERA upload.",
        payload: null,
      });
    }
  }

  return (
    <div className="space-y-4">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label htmlFor="era-file" className="block text-sm font-medium text-zinc-200">
            ERA file
          </label>
          <input
            id="era-file"
            name="file"
            type="file"
            className="block w-full rounded-md border border-zinc-700 bg-black/50 px-3 py-2 text-zinc-200 file:mr-4 file:rounded-md file:border-0 file:bg-white file:px-3 file:py-2 file:text-sm file:font-medium file:text-black"
          />
        </div>

        <button
          type="submit"
          disabled={state.status === "submitting"}
          className="inline-flex rounded-md border border-white px-4 py-2 font-medium text-white transition hover:bg-white hover:text-black disabled:cursor-not-allowed disabled:border-zinc-700 disabled:text-zinc-500"
        >
          {state.status === "submitting" ? "Uploading..." : "Upload ERA"}
        </button>
      </form>

      {state.message ? (
        <p
          className={
            state.status === "error"
              ? "rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-amber-200"
              : "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-emerald-200"
          }
        >
          {state.message}
        </p>
      ) : null}

      {state.payload ? (
        <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-black/50 p-4 text-xs text-zinc-200">
          {state.payload}
        </pre>
      ) : null}
    </div>
  );
}
