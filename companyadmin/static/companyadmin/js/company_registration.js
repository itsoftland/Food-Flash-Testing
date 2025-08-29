document.addEventListener("DOMContentLoaded", function () {
    console.log("company_registration.js loaded");

    const form = document.getElementById("companyForm");
    if (!form) {
        console.warn("Company form not found!");
        return;
    }

    const loaderOverlay = document.getElementById("loaderOverlay");
    const loaderStatus = document.getElementById("loaderStatus");
    const submitButton = form.querySelector('button[type="submit"]');

    function showLoader(message = "Submitting data...") {
        loaderOverlay.style.display = "flex";
        loaderStatus.textContent = message;
        if (submitButton) submitButton.disabled = true;
    }

    function updateLoaderStatus(message) {
        loaderStatus.textContent = message;
    }

    function hideLoader() {
        loaderOverlay.style.display = "none";
        if (submitButton) submitButton.disabled = false;
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();

        showLoader("Submitting data...");

        const payload = {
            CustomerName: form.companyname.value,
            PhoneNumber: form.phonenumber.value,
            CustomerEmail: form.companyemail.value,
            GSTNumber: form.gst.value,
            CustomerContactPerson: form.contactperson.value,
            CustomerContact: form.contactphonenumber.value,
            CustomerAddress: form.comaddress1.value,
            CustomerAddress2: form.comaddress2.value,
            CustomerState: form.state.value,
            CustomerCity: form.city.value,
            CustomerUsername: form.CustomerUsername.value,
            CustomerPassword: form.CustomerPassword.value,
            DeviceModel: "Windows",
            DeviceIdentifier1: form.companyname.value,
            DeviceType: 1,
            Version: "FoodFlash 1.00",
            ProjectName: "FoodFlash 1.00"
        };

        console.log("Sending payload:", payload);

        // Step 1: Product Registration
        fetch('/companyadmin/api/product-registration/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
             },
            body: JSON.stringify(payload)
        })
        .then(response => response.json())
        .then(regData => {
            if (regData.status === "Success") {
                updateLoaderStatus("Data received, waiting for approval...");

                const customerId = regData.CustomerId;
                const productRegistrationId = regData.ProductRegistrationId;
                const pollPayload = { CustomerId: customerId };

                const pollInterval = setInterval(() => {
                    fetch('/companyadmin/api/product-authentication/', {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'X-CSRFToken': AppUtils.getCSRFToken()
                         },
                        body: JSON.stringify(pollPayload)
                    })
                    .then(response => response.json())
                    .then(authData => {                
                        let locations = [];
                    
                        try {
                            if (typeof authData.Locations === "string") {
                                // Only attempt parsing if it's a valid JSON-like string
                                if (authData.Locations.trim().startsWith("[{") && authData.Locations.trim().endsWith("}]")) {
                                    locations = JSON.parse(authData.Locations);
                                } else {
                                    console.warn("Locations is a non-JSON string:", authData.Locations);
                                }
                            } else if (Array.isArray(authData.Locations)) {
                                locations = authData.Locations;
                            } else {
                                console.warn("Unexpected Locations format:", authData.Locations);
                            }
                        } catch (e) {
                            console.error("Failed to parse Locations:", e);
                        }
                    
                        console.log("Parsed Locations:", locations);

                        if (authData.Authenticationstatus === "Approve") {
                            clearInterval(pollInterval);
                            updateLoaderStatus("Approved! Finalizing registration...");

                            const finalData = {
                                ...payload,
                                CustomerId: customerId,
                                ProductRegistrationId: productRegistrationId,
                                Authenticationstatus: authData.Authenticationstatus,
                                AuthenticationResponse: authData
                            };

                            fetch('/companyadmin/api/register-company/', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': AppUtils.getCSRFToken()
                                },
                                body: JSON.stringify(finalData)
                            })
                            .then(res => res.json())
                            .then(result => {
                                if (result?.message) {
                                    updateLoaderStatus("Registration complete 🎉");
                                    setTimeout(() => {
                                        hideLoader();
                                        form.reset();
                                        window.location.href = "/login/";
                                    }, 1500);
                                } else if (result && typeof result === 'object') {
                                    console.log("Error condition 1:", result);
                            
                                    if (result.error) {
                                        // simple error message
                                        updateLoaderStatus(result.error);
                                    } else {
                                        // Try to find the first error message deep inside the object
                                        function findFirstError(obj) {
                                            for (const key in obj) {
                                                if (Array.isArray(obj[key]) && obj[key].length > 0) {
                                                    return obj[key][0]; // return the first error string found
                                                } else if (typeof obj[key] === 'object') {
                                                    const nestedError = findFirstError(obj[key]);
                                                    if (nestedError) return nestedError;
                                                }
                                            }
                                            return null;
                                        }
                            
                                        const firstErrorMessage = findFirstError(result) || "An error occurred.";
                                        updateLoaderStatus(firstErrorMessage);
                                    }
                            
                                    setTimeout(() => {
                                        hideLoader();
                                    }, 5000);
                            
                                } else {
                                    console.log("Error condition 2:", result);
                                    updateLoaderStatus("Unexpected server response.");
                                    hideLoader();
                                }
                            })                                                       
                            .catch(err => {
                                console.log("Error condition 3:", err);
                                updateLoaderStatus("Data not submitted due to error.");
                                setTimeout(() => {
                                    hideLoader();
                                    form.reset();
                                }, 5000);
                            });
                        }
                        else{
                            // Auth status is not "Approve", so handle error message
                            // clearInterval(pollInterval); // stop further polling
                            console.warn("Authentication failed:", authData.Authenticationstatus);
                            updateLoaderStatus(authData.Authenticationstatus); // show message like "Your licence is expired..."
                            // setTimeout(hideLoader, 5000);
                        }
                    })
                    .catch(err => {
                        console.error("Polling Error:", err);
                        clearInterval(pollInterval);
                        updateLoaderStatus("Error during authentication polling.");
                        setTimeout(() => {
                            hideLoader();
                        }, 3000);
                    });
                }, 3000);
            } else {
                updateLoaderStatus("Product Registration Failed: " + JSON.stringify(regData));
                setTimeout(() => {
                    hideLoader();
                    form.reset();
                }, 2000);
            }
        })
        .catch(error => {
            console.error("Initial registration error:", error);
            updateLoaderStatus("Failed to register product: " + error);
            setTimeout(() => {
                hideLoader();
                form.reset();
            }, 2000);
        });
    });
});

document.getElementById('togglePassword').addEventListener('click', function () {
    const passwordInput = document.getElementById('CustomerPassword');
    const toggleIcon = document.getElementById('toggleIcon');
    
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        toggleIcon.classList.remove('fa-eye-slash');
        toggleIcon.classList.add('fa-eye');
    } else {
        passwordInput.type = 'password';
        toggleIcon.classList.remove('fa-eye');
        toggleIcon.classList.add('fa-eye-slash');
    }
});
