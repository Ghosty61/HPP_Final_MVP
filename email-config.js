// Email Configuration for HPP ROI Calculator
// Uses EmailJS (https://www.emailjs.com/) for frontend email sending

const EMAIL_CONFIG = {
    // Admin email - receives all ROI form submissions
    adminEmail: "andrew@daijyov.com",

    // EmailJS credentials - replace with your EmailJS account values
    // Sign up at https://www.emailjs.com/ to get these values
    serviceId: "YOUR_EMAILJS_SERVICE_ID",
    templateId: "YOUR_EMAILJS_TEMPLATE_ID",
    publicKey: "YOUR_EMAILJS_PUBLIC_KEY",

    // Email template parameters mapping
    templateParams: {
        to_email: "andrew@daijyov.com",
        from_name: "HPP ROI Calculator",
        reply_to: "noreply@hpp-calculator.com"
    }
};
