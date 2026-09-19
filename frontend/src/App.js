import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

const API_URL = 'https://biclogicpropsearch.onrender.com/api';

function App() {
  const [formData, setFormData] = useState({
    email: '',
    phone: '',
    telegram_id: '',
    min_price: '',
    max_price: '',
    zip_codes: '',
    property_type: '',
    bedrooms: '',
    bathrooms: '',
    min_sqft: '',
    notification_frequency: 'once' // 'once', 'daily', 'weekly', 'monthly'
  });
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [validationErrors, setValidationErrors] = useState({});
  const [telegramCode, setTelegramCode] = useState(null);
  const [telegramConnected] = useState(false);
  const [codeExpiry, setCodeExpiry] = useState(null);
  const [showLoadingModal, setShowLoadingModal] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(null);

  // Update time remaining every second when code is active
  useEffect(() => {
    if (codeExpiry && telegramCode) {
      const interval = setInterval(() => {
        const remaining = Math.max(0, Math.ceil((codeExpiry.getTime() - new Date().getTime()) / 60000));
        setTimeRemaining(remaining);
        
        // Clear code if expired
        if (remaining === 0) {
          setTelegramCode(null);
          setCodeExpiry(null);
          setTimeRemaining(null);
        }
      }, 1000);
      
      return () => clearInterval(interval);
    }
  }, [codeExpiry, telegramCode]);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    // Clear validation error for this field
    setValidationErrors({
      ...validationErrors,
      [e.target.name]: ''
    });
  };

  const validateForm = () => {
    const errors = {};
    
    // Required fields
    if (!formData.email) {
      errors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      errors.email = 'Email is invalid';
    }
    
    if (!formData.zip_codes) {
      errors.zip_codes = 'At least one zip code is required';
    }
    
    // Price range validation
    if (formData.min_price && formData.max_price) {
      if (parseInt(formData.min_price) > parseInt(formData.max_price)) {
        errors.min_price = 'Min price cannot be greater than max price';
        errors.max_price = 'Max price cannot be less than min price';
      }
    }
    
    // Numeric field validation
    if (formData.bedrooms && parseInt(formData.bedrooms) < 0) {
      errors.bedrooms = 'Bedrooms cannot be negative';
    }
    if (formData.bathrooms && parseFloat(formData.bathrooms) < 0) {
      errors.bathrooms = 'Bathrooms cannot be negative';
    }
    if (formData.min_sqft && parseInt(formData.min_sqft) < 0) {
      errors.min_sqft = 'Min sqft cannot be negative';
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const generateTelegramCode = async () => {
    if (!formData.email) {
      setError('Please enter your email first');
      return;
    }

    try {
      const response = await axios.post(`${API_URL}/generate-telegram-code`, {
        email: formData.email
      });

      if (response.data.success) {
        setTelegramCode(response.data.code);
        const expiryDate = new Date(response.data.expires_at);
        const now = new Date();
        const remaining = Math.max(0, Math.ceil((expiryDate.getTime() - now.getTime()) / 60000));
        setCodeExpiry(expiryDate);
        setTimeRemaining(remaining);
        setError('');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to generate code');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Validate form
    if (!validateForm()) {
      return;
    }

    setLoading(true);
    setShowLoadingModal(true);

    try {
      const endpoint = formData.notification_frequency === 'once' ? `${API_URL}/quick-search` : `${API_URL}/subscribe`;
      const response = await axios.post(endpoint, {
        ...formData,
        min_price: formData.min_price ? parseInt(formData.min_price) : null,
        max_price: formData.max_price ? parseInt(formData.max_price) : null,
        bedrooms: formData.bedrooms ? parseInt(formData.bedrooms) : null,
        bathrooms: formData.bathrooms ? parseFloat(formData.bathrooms) : null,
        min_sqft: formData.min_sqft ? parseInt(formData.min_sqft) : null
      });

      if (response.data.success) {
        setSubmitted(true);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to submit. Please try again.');
    } finally {
      setLoading(false);
      setShowLoadingModal(false);
    }
  };

  if (submitted) {
    return (
      <div className="container">
        <div className="success-message">
          <h1>🎉 {formData.notification_frequency === 'once' ? 'Search Complete!' : 'Subscription Created!'}</h1>
          <p>{formData.notification_frequency === 'once'
            ? 'Properties matching your criteria have been sent to your email and Telegram.'
            : 'You will receive property notifications on your selected schedule.'}
          </p>
          <button onClick={() => { setSubmitted(false); }} className="btn">
            {formData.notification_frequency === 'once' ? 'Search Again' : 'Create Another Subscription'}
          </button>
        </div>
      </div>
    );
  }

  if (showLoadingModal) {
    return (
      <div className="loading-modal">
        <div className="loading-content">
          <div className="spinner"></div>
          <h2>Processing Your Request</h2>
          <p>Please do not close this window while we process your request.</p>
          <p className="loading-text">This may take a moment...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      <div className="header">
        <h1>🏠 Property Alerts</h1>
        <p>Search for properties or subscribe to recurring notifications</p>
      </div>

      <form onSubmit={handleSubmit} className="form">
        {error && <div className="error">{error}</div>}

        <div className="form-section">
          <h2>Contact</h2>
          
          <div className="form-group">
            <label htmlFor="email">Email *</label>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              required
              placeholder="your@email.com"
              className={validationErrors.email ? 'error' : ''}
            />
            {validationErrors.email && <span className="error-message">{validationErrors.email}</span>}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="phone">Phone</label>
              <input
                type="tel"
                id="phone"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                placeholder="+1 234 567 8900"
              />
            </div>

            <div className="form-group">
              <label>Telegram Connection</label>
              {telegramConnected ? (
                <div className="telegram-connected">
                  <span className="success-icon">✓</span> Connected
                </div>
              ) : telegramCode ? (
                <div className="telegram-code-display">
                  <div className="code-text">Code: <strong>{telegramCode}</strong></div>
                  <div className="code-instructions">
                    1. Open Telegram bot<br/>
                    2. Click "Connect Account"<br/>
                    3. Send this code: {telegramCode}<br/>
                    {timeRemaining !== null && <div className="code-expiry">Expires in {timeRemaining} minutes</div>}
                  </div>
                  <button type="button" onClick={generateTelegramCode} className="btn-small">
                    Generate New Code
                  </button>
                </div>
              ) : (
                <button type="button" onClick={generateTelegramCode} className="btn-small">
                  Connect Telegram
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="form-section">
          <h2>Property Criteria</h2>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="min_price">Min Price ($)</label>
              <input
                type="number"
                id="min_price"
                name="min_price"
                value={formData.min_price}
                onChange={handleChange}
                placeholder="100000"
                className={validationErrors.min_price ? 'error' : ''}
              />
              {validationErrors.min_price && <span className="error-message">{validationErrors.min_price}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="max_price">Max Price ($)</label>
              <input
                type="number"
                id="max_price"
                name="max_price"
                value={formData.max_price}
                onChange={handleChange}
                placeholder="500000"
                className={validationErrors.max_price ? 'error' : ''}
              />
              {validationErrors.max_price && <span className="error-message">{validationErrors.max_price}</span>}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="zip_codes">Zip Codes *</label>
            <input
              type="text"
              id="zip_codes"
              name="zip_codes"
              value={formData.zip_codes}
              onChange={handleChange}
              placeholder="28202, 28203, 28204"
              className={validationErrors.zip_codes ? 'error' : ''}
            />
            <small>Comma separated</small>
            {validationErrors.zip_codes && <span className="error-message">{validationErrors.zip_codes}</span>}
          </div>

          <div className="form-group">
            <label>Property Type</label>
            <div className="button-group">
              <button
                type="button"
                className={`type-btn ${formData.property_type === '' ? 'active' : ''}`}
                onClick={() => setFormData({...formData, property_type: ''})}
              >
                Any
              </button>
              <button
                type="button"
                className={`type-btn ${formData.property_type === 'house' ? 'active' : ''}`}
                onClick={() => setFormData({...formData, property_type: 'house'})}
              >
                🏠 House
              </button>
              <button
                type="button"
                className={`type-btn ${formData.property_type === 'apartment' ? 'active' : ''}`}
                onClick={() => setFormData({...formData, property_type: 'apartment'})}
              >
                🏢 Apartment
              </button>
              <button
                type="button"
                className={`type-btn ${formData.property_type === 'condo' ? 'active' : ''}`}
                onClick={() => setFormData({...formData, property_type: 'condo'})}
              >
                🏙️ Condo
              </button>
              <button
                type="button"
                className={`type-btn ${formData.property_type === 'townhouse' ? 'active' : ''}`}
                onClick={() => setFormData({...formData, property_type: 'townhouse'})}
              >
                🏘️ Townhouse
              </button>
              <button
                type="button"
                className={`type-btn ${formData.property_type === 'land' ? 'active' : ''}`}
                onClick={() => setFormData({...formData, property_type: 'land'})}
              >
                🌳 Land
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="bedrooms">Min Beds</label>
            <input
              type="number"
              id="bedrooms"
              name="bedrooms"
              value={formData.bedrooms}
              onChange={handleChange}
              placeholder="2"
              min="0"
              className={validationErrors.bedrooms ? 'error' : ''}
            />
            {validationErrors.bedrooms && <span className="error-message">{validationErrors.bedrooms}</span>}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="bathrooms">Min Baths</label>
              <input
                type="number"
                id="bathrooms"
                name="bathrooms"
                value={formData.bathrooms}
                onChange={handleChange}
                placeholder="1"
                min="0"
                step="0.5"
                className={validationErrors.bathrooms ? 'error' : ''}
              />
              {validationErrors.bathrooms && <span className="error-message">{validationErrors.bathrooms}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="min_sqft">Min Sqft</label>
              <input
                type="number"
                id="min_sqft"
                name="min_sqft"
                value={formData.min_sqft}
                onChange={handleChange}
                placeholder="1000"
                min="0"
                className={validationErrors.min_sqft ? 'error' : ''}
              />
              {validationErrors.min_sqft && <span className="error-message">{validationErrors.min_sqft}</span>}
            </div>
          </div>
        </div>

        <div className="form-section">
          <h2>Notification Frequency</h2>
          <div className="form-group">
            <label htmlFor="notification_frequency">How often?</label>
            <select
              id="notification_frequency"
              name="notification_frequency"
              value={formData.notification_frequency}
              onChange={handleChange}
            >
              <option value="once">One-time only</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          Submit
        </button>
      </form>

      <div className="info-section">
        <h3>How it works</h3>
        <ol>
          <li>Enter your contact info and property preferences</li>
          <li>Choose notification frequency: once, daily, weekly, or monthly</li>
          <li>We search for matching properties and send you email and Telegram notifications</li>
        </ol>
      </div>
    </div>
  );
}

export default App;
