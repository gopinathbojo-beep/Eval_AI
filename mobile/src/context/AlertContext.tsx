import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { Alert, AlertButton, AlertOptions } from "react-native";
import { AppModalPopup, AppPopupConfig, PopupType } from "../components/AppModalPopup";

interface AlertContextType {
  showAlert: (config: Omit<AppPopupConfig, "visible">) => void;
  hideAlert: () => void;
}

const AlertContext = createContext<AlertContextType | undefined>(undefined);

// Reference for global interceptor dispatch
type AlertPayload = {
  title: string;
  message?: string;
  buttons?: AlertButton[];
  options?: AlertOptions;
};

let globalAlertDispatcher: ((payload: AlertPayload) => void) | null = null;

// Native reference backup
const nativeAlert = Alert.alert;

// Global Alert.alert interceptor
Alert.alert = (
  title: string,
  message?: string,
  buttons?: AlertButton[],
  options?: AlertOptions
) => {
  if (globalAlertDispatcher) {
    globalAlertDispatcher({ title, message, buttons, options });
  } else {
    nativeAlert(title, message, buttons, options);
  }
};

export const AlertProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [popupConfig, setPopupConfig] = useState<AppPopupConfig>({
    visible: false,
    title: "",
  });

  const showAlert = useCallback((config: Omit<AppPopupConfig, "visible">) => {
    setPopupConfig({ ...config, visible: true });
  }, []);

  const hideAlert = useCallback(() => {
    setPopupConfig((prev) => ({ ...prev, visible: false }));
  }, []);

  useEffect(() => {
    globalAlertDispatcher = ({ title, message, buttons }: AlertPayload) => {
      let type: PopupType = "info";
      const titleLower = (title || "").toLowerCase();
      const messageLower = (message || "").toLowerCase();

      if (
        titleLower.includes("error") ||
        titleLower.includes("fail") ||
        titleLower.includes("cannot") ||
        titleLower.includes("reject") ||
        messageLower.includes("failed") ||
        messageLower.includes("error")
      ) {
        type = "error";
      } else if (
        titleLower.includes("success") ||
        titleLower.includes("verified") ||
        titleLower.includes("complete") ||
        titleLower.includes("approved") ||
        titleLower.includes("confirmed") ||
        titleLower.includes("done") ||
        messageLower.includes("successfully") ||
        messageLower.includes("verified and locked")
      ) {
        type = "success";
      } else if (
        titleLower.includes("warning") ||
        titleLower.includes("delete") ||
        titleLower.includes("remove") ||
        titleLower.includes("incomplete") ||
        titleLower.includes("required") ||
        titleLower.includes("finalize") ||
        titleLower.includes("validation") ||
        titleLower.includes("unresolved")
      ) {
        type = "warning";
      }

      if (!buttons || buttons.length === 0) {
        setPopupConfig({
          visible: true,
          title: title || "",
          message: message || "",
          type,
          confirmText: "OK",
          onConfirm: () => {},
        });
        return;
      }

      if (buttons.length === 1) {
        const btn = buttons[0];
        setPopupConfig({
          visible: true,
          title: title || "",
          message: message || "",
          type,
          confirmText: btn.text || "OK",
          onConfirm: btn.onPress,
        });
        return;
      }

      // 2 or more buttons: identify cancel button vs action button
      const cancelBtn = buttons.find((b) => b.style === "cancel") || buttons[0];
      const actionBtn = buttons.find((b) => b !== cancelBtn) || buttons[1];

      setPopupConfig({
        visible: true,
        title: title || "",
        message: message || "",
        type: actionBtn?.style === "destructive" ? "warning" : type,
        cancelText: cancelBtn?.text || "Cancel",
        onCancel: cancelBtn?.onPress,
        confirmText: actionBtn?.text || "Confirm",
        onConfirm: actionBtn?.onPress,
        isDestructive: actionBtn?.style === "destructive",
      });
    };

    return () => {
      globalAlertDispatcher = null;
    };
  }, []);

  return (
    <AlertContext.Provider value={{ showAlert, hideAlert }}>
      {children}
      <AppModalPopup config={popupConfig} onClose={hideAlert} />
    </AlertContext.Provider>
  );
};

export const useAlert = () => {
  const context = useContext(AlertContext);
  if (!context) {
    throw new Error("useAlert must be used within an AlertProvider");
  }
  return context;
};
