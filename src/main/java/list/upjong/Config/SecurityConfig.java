package list.upjong.Config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .cors(Customizer.withDefaults()) //CORS 설정 사용
                .csrf(csrf -> csrf.disable()) //CSRF 비활성화
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().permitAll() //모든 요청 허용

                );

        return http.build();
    }
}
