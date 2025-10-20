import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

/**
 * Custom hook for team mutation operations with consistent error/success handling
 */
export function useTeamMutation() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const resetMessages = () => {
    setError(null);
    setSuccess(null);
  };

  const showSuccess = (message: string) => {
    setSuccess(message);
    toast.success(message);
  };

  const showError = (error: unknown, fallbackMessage = "An error occurred") => {
    const errorMessage = extractErrorMessage(error, fallbackMessage);
    setError(errorMessage);
    toast.error(errorMessage);
  };

  return {
    error,
    success,
    setError,
    setSuccess,
    showSuccess,
    showError,
    resetMessages,
    qc,
  };
}

/**
 * Extract error message from various error formats
 */
export function extractErrorMessage(
  error: unknown,
  fallback = "An error occurred"
): string {
  if (typeof error === "string") return error;

  if (error && typeof error === "object") {
    const err = error as any;

    // Axios error format
    if (err.response?.data?.detail) {
      const detail = err.response.data.detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }

    // Standard Error object
    if (err.message) {
      return err.message;
    }
  }

  return fallback;
}
