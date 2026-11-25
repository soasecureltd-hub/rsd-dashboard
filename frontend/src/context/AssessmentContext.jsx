import React, { createContext, useContext, useReducer } from 'react';

const AssessmentContext = createContext(null);

const initialState = {
  assessment: null,
  findings: null,        // {concerns, strengths, risk_velocity, unusual_combination}
  predictions: null,     // estimated threat likelihoods
  loading: false,
  error: null,
  activeTab: 'input',
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    case 'SET_ASSESSMENT':
      return { ...state, assessment: action.payload, findings: null, predictions: null, activeTab: 'results', error: null };
    case 'SET_FINDINGS':
      return { ...state, findings: action.payload };
    case 'SET_PREDICTIONS':
      return { ...state, predictions: action.payload };
    case 'SET_TAB':
      return { ...state, activeTab: action.payload };
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

export function AssessmentProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <AssessmentContext.Provider value={{ state, dispatch }}>
      {children}
    </AssessmentContext.Provider>
  );
}

export function useAssessment() {
  const ctx = useContext(AssessmentContext);
  if (!ctx) throw new Error('useAssessment must be used inside AssessmentProvider');
  return ctx;
}
