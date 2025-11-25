// Code generated with assistance from Gemini
// Date generated: Nov 2025
// Modified for ICT1011 Project to interact with server.

package com.example.test

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.StrictMode
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import java.io.BufferedWriter
import java.io.OutputStreamWriter
import java.net.CookieHandler
import java.net.CookieManager
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class LoginActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        // Allow network operations on the main thread (for simplicity, not recommended for production)
        val policy = StrictMode.ThreadPolicy.Builder().permitAll().build()
        StrictMode.setThreadPolicy(policy)

        // Set up a default cookie manager to handle cookies automatically
        CookieHandler.setDefault(CookieManager())

        val username = findViewById<EditText>(R.id.username)
        val password = findViewById<EditText>(R.id.password)
        val loginButton = findViewById<Button>(R.id.login_button)

        loginButton.setOnClickListener {
            val user = username.text.toString()
            val pass = password.text.toString()

            Thread {
                try {
                    val url = URL("http://103.213.247.25:8000/auth/login")
                    val conn = url.openConnection() as HttpURLConnection
                    conn.requestMethod = "POST"
                    conn.doOutput = true
                    conn.instanceFollowRedirects = false // Important to handle redirects manually to check headers

                    val params = "username=${URLEncoder.encode(user, "UTF-8")}&password=${URLEncoder.encode(pass, "UTF-8")}"
                    val writer = BufferedWriter(OutputStreamWriter(conn.outputStream, "UTF-8"))
                    writer.write(params)
                    writer.flush()
                    writer.close()

                    val responseCode = conn.responseCode

                    // The server redirects on successful login (303)
                    if (responseCode == HttpURLConnection.HTTP_SEE_OTHER) {
                        // The CookieManager will automatically handle the "Set-Cookie" header.
                        // We can now proceed to the main activity.
                        runOnUiThread {
                            startActivity(Intent(this, MainActivity::class.java))
                            finish()
                        }
                    } else {
                        // Handle failed login
                        runOnUiThread {
                            Toast.makeText(this, "Login Failed", Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                    runOnUiThread {
                        Toast.makeText(this, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }.start()
        }
    }
}