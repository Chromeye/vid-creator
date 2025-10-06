import { createContext, ReactNode, useContext, useState } from 'react';

// Define the shape of your context data

// Create the context
const MyContext = createContext(undefined);

// Create a custom hook for using the context
// eslint-disable-next-line react-refresh/only-export-components
export const useMyContext = () => {
  const context = useContext(MyContext);
  if (!context) {
    throw new Error('useMyContext must be used within a MyContextProvider');
  }
  return context;
};

export const MainContextProvider = ({ children, initialValues }) => {
  const [data, setData] = useState(initialValues);

  const updateValue = (key, value, id, format) => {
    setData((prevData) => {
      if (id) {
        // If an ID is provided, update or remove the item in the inputs array
        const updatedInputs = { ...prevData.inputs };
        if (value !== '') {
          updatedInputs[id] = { key: key, value: value, format: format };
        } else {
          delete updatedInputs[id];
        }
        return { ...prevData, inputs: updatedInputs };
      } else {
        // If no ID is provided, update or remove the entry in the existing data object
        const updatedData = { ...prevData };
        if (value !== '') {
          updatedData[key] = value;
        } else {
          delete updatedData[key];
        }
        return updatedData;
      }
    });
  };

  const removeInputsByID = (id) => {
    setData((prevData) => {
      const updatedInputs = { ...prevData.inputs };
      for (const key in updatedInputs) {
        if (key.includes(id)) {
          delete updatedInputs[key];
        }
      }
      return { ...prevData, inputs: updatedInputs };
    });
  };

  const resetData = () => {
    setData(initialValues);
  };

  const resetInputsData = () => {
    setData((prevData) => {
      return { ...prevData, inputs: {} };
    });
  };

  const contextValue = {
    data,
    updateValue,
    resetData,
    resetInputsData,
    removeInputsByID,
  };

  return <MyContext.Provider value={contextValue}>{children}</MyContext.Provider>;
};
